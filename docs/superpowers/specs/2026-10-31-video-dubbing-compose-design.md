# MangaDock 阶段四设计：视频、配音与合成导出

- 日期：2026-10-31
- 状态：待用户批准

## 意图

把阶段三的 Storyboard 和关键帧变成可播放、可下载的单集漫剧。用户可以为不同分镜段选择擅长的视频后端，逐句生成配音，并只重跑失败镜头，而不重新生成整集。

## 目标

- 统一 VideoProvider 与 TTSProvider 接口，业务代码不直接调用厂商 SDK。
- 实现 Wan、Seedance、MiniMax H3 和 Mock 视频后端。
- 实现 Edge-TTS 和 Mock TTS 后端。
- 逐句配音、逐镜渲染、ffmpeg 单集合成，导出 1080p MP4 与 SRT。
- 支持段级后端路由、段/镜进度、单镜重试、播放器字幕开关和下载。
- 不接真实服务也能通过真实 Celery、PostgreSQL、ffmpeg 和 HTTP 路径验收全流程。

## 非目标与反目标

- 不做计费、多租户、场景图生成、口型同步、声音克隆、背景音乐创作或整剧批量导出。
- 不为了适配后端而放宽最终镜头 2–5 秒、段不超过 15 秒的约束。
- 不静默加速超长配音、不省略失败台词、不用静态图片冒充真实 Provider 的成功结果。
- 不在 MVP 引入分布式任务系统或独立限流服务。

## 已确认的决策

- 新增独立 `video_providers` 表，并修订 ADR 0003；不再用旧 `llm_providers` 的 video 能力作为阶段四实际视频后端配置。
- TTS 首版使用 Edge-TTS；无需 API Key，接受其网络依赖和音色映射限制。
- Wan 使用当前镜头自然语言；Seedance 使用分字段当前镜头提示词；MiniMax H3 使用官方三字段结构并保留段级上下文。
- 对最低生成时长高于目标镜头的后端，按后端最低时长生成，再精确裁剪到 Storyboard 时长。
- Celery 按段并行，段内异步生成镜头，Provider 并发由信号量限制。
- 同时导出烧录字幕版和干净版；干净版通过 WebVTT 提供真正的播放器字幕开关。
- 配音总时长超过所属镜头时，该台词标记失败并停止后续合成，不自动加速或延长镜头。

## 备选方案

### Provider 配置

独立 `video_providers` 表被采用，因为视频后端类型、模型参数和段级路由已与 LLM 配置不同。复用 `llm_providers` 虽能减少 CRUD，但会继续混合不兼容的配置语义。

### 渲染调度

采用“Celery 段任务 + 段内 asyncio”而非整集单任务或每镜一个 Celery 任务。前者恢复与路由清晰，后两者分别削弱段级恢复或显著增加队列及限流复杂度。

### 字幕

采用烧录版与干净版双输出。只输出烧录版无法实现真正字幕开关；只输出干净版又不满足烧录交付要求。

## Provider 边界

### VideoProvider

位于 `packages/providers`，不修改 LLMProvider 或 ImageProvider：

```python
async def generate(
    keyframe_image: str,
    prompt: str,
    duration_s: int,
    config: Mapping[str, Any],
) -> VideoResult:
    ...
```

`VideoResult` 包含本地 `path`、实际 `duration_s`、宽高、格式、Provider 名称及元数据。`duration_s` 是本次生成请求的目标镜头时长；后端最低时长差异由具体 Provider 在 `min_duration_s` 中处理，结果元数据保留 `source_duration_s`。

Provider 只处理连接、提交、轮询、下载和稳定异常。Prompt 由并列的独立构建器生成：

- `wan_prompt.build(segment, cut_index)`：首帧一致性、角色、场景、动作、运镜和当前镜头时长。
- `seedance_prompt.build(segment, cut_index)`：`[首帧参考]`、`[角色与场景]`、`[动作与运镜]`、`[输出]`。
- `minimax_h3_prompt.build(segment, cut_index)`：
  - `integrated_multimodal_description`：段内 `[Shot N]`、时间码、当前镜头标记与上下文。
  - `overall_soundscape`：无额外对白，保留必要环境声。
  - `non_diegetic_music`：无背景音乐，避免与独立配音冲突。

构建器位于 providers 包而非 core，单测对同一 Segment 断言三种格式，Provider 内不硬编码其他厂商格式。

### WanProvider

复用阶段三 ComfyUI 的 base_url、api_key_env、模板目录和 HTTP 连接方式。抽取内部 ComfyUI 客户端辅助代码以上传首帧、提交工作流、轮询 history 和下载媒体；ImageProvider 公共接口不变。

新增 `wan_i2v_v1.json`，以 Wan2.2 TI2V 5B 工作流为基线，使用 `Wan22ImageToVideoLatent`。视频 history 输出兼容 `videos` 与 `gifs` 节点输出。模型文件说明采用：

```text
ComfyUI/models/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors
ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
ComfyUI/models/vae/wan2.2_vae.safetensors
```

### SeedanceProvider

直接使用 httpx 调用火山方舟，不引入厂商 SDK：

- `POST {base_url}/contents/generations/tasks`
- `GET {base_url}/contents/generations/tasks/{task_id}`
- 从 `content.video_url` 下载 MP4。

请求包含模型、文本与首帧 `image_url`、时长、宽高比、水印和禁用原生音频。默认 `min_duration_s=4`，可在记录配置中覆盖以支持允许 2 秒的模型。

### MinimaxH3Provider

直接使用 httpx 调用：

- `POST {base_url}/v2/video_generation`
- 查询任务直至 `succeeded`，从 `task.content.url` 下载。
- 首帧使用 `role=first_frame`，`min_duration_s=4`。

首版不在每镜额外调用 H3-Context-IR；本地构建器直接产出与其兼容的三字段 Prompt，保持每次镜级调用确定且可测试。

### 远程首帧

Seedance 与 MiniMax 默认把本地关键帧编码为 Base64 Data URL。记录配置也可提供 `public_asset_base_url`，此时按每个 cut 的关键帧相对路径生成独立公网 URL，而不是用一张固定图片覆盖所有镜头。限制输入大小并返回明确配置错误，不把容器本地路径发送给远程服务。

### MockVideoProvider

用 ffmpeg 生成带时长和镜标识的真实 MP4，保留同一 schema、文件读取、裁剪和合成路径。支持测试注入单次失败和并发观测，不访问网络。

## TTSProvider

```python
async def synthesize(
    text: str,
    voice_profile: str,
    emotion: str,
) -> AudioResult:
    ...
```

`AudioResult` 包含音频路径、实测 duration_s、格式、采样率与元数据。

### EdgeTTSProvider

使用 `edge-tts` 生成 MP3，通过 ffprobe 实测时长。中文自由文本 `voice_profile` 不能直接当作 Edge 音色 ID，因此使用确定性的映射器：

- 显式角色/角色卡映射优先，来自 `EDGE_TTS_VOICE_MAP` JSON。
- 男声、女声、语速、音调关键词映射到配置允许列表。
- 无匹配时使用 `EDGE_TTS_DEFAULT_VOICE`，情绪只调整配置允许的 rate/pitch，不声称理解自然语言音色描述。

### MockTTSProvider

用标准库生成有效 WAV，按中文 4.5 字/秒估算并设置最短时长；帧数与返回 duration_s 一致。可注入失败，不访问网络。

## 数据契约与持久化

新增 schema，均位于 `packages/core/schemas/`：

### Dubbing

```json
{
  "episodes": [{
    "episode": 1,
    "lines": [{
      "line_id": "1:1:2",
      "scene": 1,
      "order": 2,
      "segment": 1,
      "cut": 1,
      "character": "林夏",
      "text": "你还是不肯说出真相吗？",
      "emotion": "震惊",
      "audio_path": "projects/1/audio/episode_1/1-1-2.mp3",
      "start_s": 0.0,
      "duration_s": 2.667,
      "end_s": 2.667,
      "status": "done",
      "error": null
    }]
  }]
}
```

`line_id` 使用 `episode:scene:order`。校验台词与 Script/Storyboard 引用一一对应、ID 唯一、时长非负、`end_s=start_s+duration_s`。cut 时间窗约束只作用于 `status=done` 的台词；失败台词保留实测 start/duration/end 以便诊断，即使 duration 已超过 cut。失败资产不能进入 Render。时间轴按 Storyboard cut 时长累计；同镜多句按原顺序连续排列。

### Render

按 episode → segment → cut 保存每镜 `status`、`attempt_count`、`provider_id`、`clip_path`、`duration_s`、`source_duration_s`、`source_fingerprint` 与 `error`。段和集进度由镜状态计算，不另存可失真的百分比。只有 fingerprint 与当前输入一致的成功 clip 才可保留。

### Compose

按集保存干净版、烧录版、SRT、WebVTT 的相对路径、时长、宽高、状态与 `source_fingerprint`。所有数据库与 API 路径均相对 `ASSET_ROOT`，沿用阶段三 `/api/v1/assets/{path}` 安全读取。

### 依赖指纹与失效

使用规范 JSON 的 SHA-256，避免“文件存在但内容已过期”被误复用：

- Dubbing：Script 集、角色 voice_profile、TTS 模式与配置。
- Render 每镜：cut、关键帧相对路径、相关 Dubbing 行、VideoProvider 类型/配置/更新时间和视频模式。
- Compose：本集成功镜 fingerprint、Dubbing fingerprint、字幕和合成配置。

锚点重建仍清空 Storyboard 关键帧，同时把 Dubbing/Render/Compose 阶段和资产标记 outdated。后续重试只复用 fingerprint 不变的成功项；视频 Provider 或段路由变化只重渲染受影响镜，音色变化只重做受影响配音，字幕变化只重新合成。

### 新表

- `video_providers`：`name`（唯一）、`kind`（wan/seedance/minimax_h3）、`base_url`、`model`、`api_key_env`、`enabled`、`config_json`、时间戳。密钥值仍只存在环境变量中。
- `project_video_routes`：`project_id`、`episode`、`segment_index`、`video_provider_id`，三元组唯一。只允许 `(0,0)` 项目默认和 `(episode>0,segment>0)` 精确段路由；先查精确段，再查项目默认。fake 模式两者都缺省时使用 MockVideoProvider，live 模式返回明确配置错误。

新增表继续通过启动时 `create_all` 创建；Alembic 仍是独立遗留项。旧 `project_provider_routes.role=video` 保留兼容展示，不隐式迁移或作为新渲染后端。

## 管线状态机

用户点击“开始渲染”后才产生 TTS/视频外部调用，避免 Storyboard 完成即产生费用。MVP 同一项目只允许一个活跃渲染/合成 episode；重复 POST 在活跃期返回 409，单镜重试只在 render=failed 时允许，避免重复付费调用和项目级资产竞争。不同项目可并行。

1. API 校验 Storyboard 完整、关键帧存在、Provider enabled 和路由合法，保存默认/段级路由。请求中的 `video_provider_id` 更新 `(0,0)` 项目默认，会影响后续未设置精确段路由的集。
2. 根据依赖 fingerprint 仅重置目标 episode 的过期 Dubbing/Render/Compose 项，其他集与输入未变的成功镜不受影响。
3. 无有效 Dubbing 时运行 `stage_dubbing`，逐句合成并实测时长；若已有合法资产则跳过。
4. `stage_render` 创建/更新 render.json，以 Celery chord 并行段任务。
5. 每个段任务用 asyncio gather 生成镜，Provider 信号量限制同后端并发。每镜最多两次尝试，之后标记 failed。
6. chord 全部结束后汇总；有失败则 render=failed 且不合成，全部成功才运行 `stage_compose`。
7. 单镜重试只重置该镜并 enqueue 对应段任务；汇总时若全镜成功，继续 compose，不重复 LLM、TTS 或其他视频镜。
8. 阶段间 enqueue 失败落库为 failed/retryable，沿用阶段三修复后的处理方式。

Provider 并发取记录 `max_concurrency`、环境全局上限和 Worker 实际能力的最小值。首版信号量只约束单 Worker 进程，ADR 明确多实例需要后续分布式限流。

## ffmpeg 合成

每个 clip 统一转码为 H.264、yuv420p、24 fps，并裁剪到 cut.duration_s。合成时以 1920×1080 为目标等比缩放并填充，不拉伸角色。

- 按 Storyboard 顺序 concat clips。
- 按 Dubbing start_s 延迟每句音频并混音；无台词处保持静音。
- 用同一 Dubbing 时间轴生成 SRT 与 WebVTT，毫秒换算统一由 core 函数处理。
- `episode_{n}.mp4`：烧录字幕版。
- `episode_{n}_clean.mp4`：无烧录字幕的播放器版本。
- `episode_{n}.srt`：独立下载字幕。
- `episode_{n}.vtt`：HTML track 字幕。

字体、字号、位置和描边通过环境变量配置。ffmpeg 对字幕路径和文本使用安全转义，不把台词拼入 shell 字符串；所有命令用参数数组执行。Worker Dockerfile 安装 ffmpeg/ffprobe，Compose 继续共享 `mangadock_assets`。

## API

沿用 `/api/v1`：

- `POST/GET /video-providers`，`PATCH/DELETE /video-providers/{id}`；引用保护同现有 Provider。
- `POST /projects/{id}/episodes/{n}/render`：接收可选默认 `video_provider_id` 与 `segment_providers` 映射，启动/恢复渲染。
- `GET /projects/{id}/episodes/{n}/render`：段→镜状态、完成数、Provider、错误和产物。
- `POST /projects/{id}/episodes/{n}/segments/{segment}/cuts/{cut}/retry`：单镜重试。
- `GET /projects/{id}/episodes/{n}/export`：合成状态及四类下载路径。
- `GET /api/v1/assets/{path}`：复用于音频、MP4、SRT 和 VTT。

API 只做校验、状态写入与入队，不同步执行 TTS、视频或 ffmpeg。活跃 episode 的重复渲染和运行中单镜重试统一返回 409，不创建第二条 chord。

## 前端

项目详情新增“成片”区域：

- 默认后端及逐段后端选择，开始渲染按钮。
- 段→镜进度、失败原因和单镜重试。
- 合成完成后显示播放器、字幕开关、烧录版/干净版/SRT 下载。
- 播放器使用 clean MP4 + WebVTT track；烧录版作为独立下载，不误导用户字幕可关闭。
- 继续显示现有模型协作，并将视频默认路由接入新 video_providers。

## 环境变量

- 模式：`MANGADOCK_VIDEO_MODE`、`MANGADOCK_TTS_MODE`，均可独立为 fake/live。
- Wan：`COMFYUI_API_KEY`（可空）、`COMFYUI_TEMPLATE_DIR`；连接和模型在 video_providers 记录中。
- Seedance：`ARK_API_KEY`。
- MiniMax：`MINIMAX_API_KEY`。
- Edge-TTS：`EDGE_TTS_DEFAULT_VOICE`、`EDGE_TTS_VOICE_MAP`、`EDGE_TTS_RATE`、`EDGE_TTS_PITCH`。
- 渲染：`VIDEO_PROVIDER_TIMEOUT_S`、`VIDEO_MAX_CONCURRENCY`、`FFMPEG_BIN`、`FFPROBE_BIN`。
- 字幕：`SUBTITLE_FONT`、`SUBTITLE_FONT_SIZE`、`SUBTITLE_ALIGNMENT`、`SUBTITLE_OUTLINE`。

`.env.example` 只放空密钥和安全默认值，README 列出每个 Provider 的必填/可选项及 Mock 步骤。

## 测试与验收

- Prompt 构建器：同一 Segment 断言 Wan、Seedance、H3 格式、当前镜和段上下文。
- Provider：respx 覆盖提交、排队、成功、失败、超时、下载、最低时长和首帧编码；ComfyUI 视频输出单独覆盖。
- Schema：台词覆盖、时间码、超长配音失败行、渲染状态、路径与资产校验。
- 依赖指纹：锚点/关键帧、音色、Provider、段路由和字幕变化只失效对应下游资产。
- Worker：Mock 三层跑通 Storyboard → Dubbing → Render → Compose；ffprobe 验证 1080p 和时长，SRT/WebVTT 与配音时长一致。
- 单镜首次失败、第二次成功；永久失败后仅该镜重试，其他 Provider 调用次数不增加。
- 段内并行和 Provider 并发上限；enqueue 失败状态；活跃 episode 重复 POST 与运行中单镜重试返回 409。
- API：路由优先级、进度、单镜重试、导出下载、跨项目访问与配置错误。
- 前端：后端选择、进度、重试、播放、字幕开关和下载。
- Compose：全新 Mock 项目走真实 HTTP/Celery/PostgreSQL/ffmpeg，播放器播放 clean MP4，检查四个产物。

真实 Wan/Seedance/MiniMax/Edge-TTS 验收需要用户环境或密钥；没有凭据时不得声称已验证真实服务。

## ADR 与文档

- 新增 ADR 0005：Prompt 构建器拆分、Edge-TTS 选型、段/镜并行和单 Worker 限流取舍、最低时长裁剪与双字幕版本。
- 修订 ADR 0003：独立 video_providers 替代旧 video 能力作为实际渲染配置。
- 修订 AGENTS.md：删除“MVP 不实现 TTS”禁区，补充 ffmpeg/媒体产物约定。
- README：环境变量、模型文件、Mock 全流程、真实服务边界和下载说明。

## 官方接口依据

- Seedance 视频任务与首帧输入：https://www.volcengine.com/docs/82379/1366799
- MiniMax H3 视频生成：https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create
- MiniMax H3-Context-IR：https://platform.minimaxi.com/docs/api-reference/video-generation-v2-h3-context-ir
- Wan2.2 ComfyUI 工作流：https://docs.comfy.org/tutorials/video/wan/wan2_2

## 留给实现者的决定

不影响交付范围的细节可由实现者按现有代码风格决定，包括内部模块命名、Pydantic 辅助函数、ffmpeg 具体过滤图组织、前端组件拆分和测试 fixture 复用。任何改变上述公共接口、时间轴语义、路由或失败恢复行为的决定都必须回到本设计。
