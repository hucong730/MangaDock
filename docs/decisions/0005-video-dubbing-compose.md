# ADR 0005：视频后端、配音与合成导出

- 状态：已接受
- 日期：2026-10-31

## 背景

阶段四需要从 Storyboard 生成单集成片。视频后端的 Prompt 与最短时长不同，配音需要实测时间轴，渲染还必须支持段级模型选择、单镜恢复和可复用资产。

## 决策

### 独立 Prompt 构建器

VideoProvider 只负责连接、提交、轮询和下载。Wan 使用当前镜头自然语言，Seedance 使用分字段提示词，MiniMax H3 使用 `integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music` 三字段并保留段级上下文。构建器并列放在 providers 包，禁止在 Provider 内混入其他厂商格式，也避免 core 依赖厂商规则。

最低时长高于目标的后端先按最低时长生成，再由 ffmpeg 精确裁剪，最终镜头仍严格保持 2–5 秒。段内时间码和 SRT/WebVTT 只来自实测配音时长。

### Edge-TTS

首版真实 TTS 采用 Edge-TTS：无需 API Key、中文音色丰富、依赖轻，适合本地 MVP。代价是依赖微软服务网络，且自由文本音色提示词只能确定性映射到音色、语速和音调，不等于声音克隆。MockTTS 用有效 WAV 验证相同时间轴与合成路径。

### 段/镜并行与限流

Celery chord 按 segment 并行，segment 内用 asyncio 并行 cuts。每个 Provider 使用进程内信号量，取配置上限和全局上限的较小值。该方案保留段级路由与恢复，避免每镜一个 Celery 消息的开销。信号量只约束单 Worker 进程；多实例部署需要后续分布式限流。

### 依赖指纹与失败恢复

Dubbing、Render 和 Compose 保存来源指纹。只有 Script、关键帧、音色、Provider、路由、字幕配置均未变化的成功资产才可复用。配音指纹精确到台词，单个角色音色变化只重做该角色台词。锚点变化会使全部下游过期；Provider/路由变化只重建受影响镜头。单镜最多尝试两次，之后只重试目标镜，其他成功或失败镜保持不变。段间按镜合并数据库状态，入队和失效检查在事务内完成，避免重复付费调用与旧快照覆盖。

### 下载安全与时长

厂商 Bearer 凭证只用于对应 API，不随视频下载 URL 转发到 CDN。下载后使用 ffprobe 实测时长，明显短于请求时长的结果视为失败，禁止用 `-t` 掩盖缺帧。合成阶段再次校验依赖指纹，防止旧输出覆盖新输入。

### 双字幕版本

`episode_{n}.mp4` 为烧录版，`episode_{n}_clean.mp4` 为播放器版本，另导出 SRT 与 WebVTT。烧录字幕无法通过播放器关闭，因此用 clean + WebVTT 实现真正的字幕开关。所有输出统一为 1920×1080、24 fps。

## 影响

- 新增 `video_providers` 和 `project_video_routes`，精确段路由优先于 `(0,0)` 项目默认。
- API 同一项目仅允许一个活跃渲染/合成 episode，避免重复付费调用和项目资产竞争。
- ffmpeg 只以参数数组执行；数据库只存 ASSET_ROOT 相对路径和环境变量名。
- 真实 Wan/Seedance/MiniMax/Edge-TTS 需要各自环境验收，Mock 通过不能替代真实服务证明。
