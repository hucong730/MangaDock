# MangaDock 阶段三：角色锚点、参考图与分镜设计

## 目标

从阶段二 Outline/Script 生成角色圣经、可确认的角色锚点图及多视图，以及经过硬校验的分镜和关键帧。新增 ImageProvider 与 ComfyUI 后端，MockImageProvider 可在无 ComfyUI 时完成全流程。

## 已确认方案

- 复用 llm_providers/provider_capabilities/project_provider_routes，不新增 image_providers 表；图像模型走 image 能力和项目路由。
- LLM 继续走 LLMProvider.chat；core 不直接调用 ComfyUI。
- 角色正面全身锚点图必须人工确认，其他视图只能以确认图为参考。
- episode → segments（≤15s）→ cuts（2–5s），关键帧参考角色锚点，scene_ref 本期为 null。
- 项目 API 使用 /api/v1/projects，资产通过受控路径读取。

## ImageProvider 与 ComfyUI

### 接口

```python
async def generate(
    self,
    prompt: str,
    reference_images: Sequence[str],
    size: tuple[int, int],
) -> ImageResult:
    ...
```

ImageResult 包含 path、width、height、format、workflow_id 和 metadata。MockImageProvider 返回本地小 PNG；ComfyUIProvider 通过 HTTP 返回真实图片，异常分类为配置、传输、API、响应和超时。

### 模板

模板位于 packages/providers/comfyui/templates，使用原生节点 UNETLoader、CLIPLoader、VAELoader、TextEncodeQwenImage21、KSampler、VAEDecode、SaveImage，以及参考图所需的 LoadImage。采用 int8 convrot 模型与 bf16 VAE。

- character_anchor_v1：Text to Image，正面全身，无参考图。
- character_views_v1：Image Edit，以确认锚点为 images.image_1，生成 avatar/profile/back/detail。
- storyboard_keyframe_v1：Image Edit，角色锚点为 images.image_1，scene_ref 为空，阶段四预留 images.image_2。

模板带独立 workflow_id 和占位符，provider 替换 prompt、negative、width、height、seed、reference_image_1。参考图先通过 /upload/image 上传，再将返回文件名交给 LoadImage。

### 调用与存储

POST /prompt 提交，GET /history/{prompt_id} 轮询，GET /view 下载。轮询间隔和超时可配置，默认 2s/300s。结果保存到 ASSET_ROOT/projects/{id}/images，API 通过 /api/v1/assets/{path} 防止目录穿越地读取。Compose 使用命名卷 mangadock_assets 共享 worker 与 API。

## 数据契约

### CharacterBible

characters[] 每项：name、biography、prompt_zh、prompt_en、voice_prompt、anchor_features（5–8 个非空短语）。validator 要求角色集合与 Outline cast 完全一致、特征去重。

CharacterImage：label、status、path/尺寸/format/workflow_id/error。front_full 为唯一锚点标签；其他为 avatar、profile、back、detail。

### Storyboard

- episodes[]：episode、segments。
- segments[]：index、duration_s（cuts 求和且 ≤15）、cuts。
- cuts[]：index、duration_s（2–5）、characters、prompt、camera、line_refs、scene_ref、keyframe_image。
- line_refs：scene + order，必须指向 Script 中真实台词；全部 Script 集与全部台词必须按原顺序且恰好出现一次，动作描写可合并。
- characters 必须属于 cast；每个出场角色至少一条 anchor_features 短语逐字出现在 prompt 中。
- 集号/段号/镜号从 1 连续，scene_ref 本期为 null，keyframe_image 可为空直到生成完成。
- 多角色同镜最多传入 4 张锚点图，images.image_1…4 与 <image1>…<image4> 一一对应，不做图片拼接。

## 持久化与状态

新增：

- CharacterRecord：项目角色设定、锚点特征、anchor_confirmed。
- CharacterImageRecord：每图独立状态、路径、workflow_id、错误。
- ProjectAssetRecord：kind=characters/storyboard 的 JSON 资产，避免修改旧表。

project_stages 新增 characters、storyboard。characters 支持 waiting_confirmation；所有锚点确认且其他视图完成后转 done。storyboard 在 characters done 后启动。单图失败只标记该图，其他任务继续。

## 管线顺序

1. Script done 后触发 stage_characters。
2. LLM 生成 CharacterBible，校验 cast 和特征。
3. 每角色生成 front_full，stage 转 waiting_confirmation；失败只标该图。
4. API 确认 front_full 后才允许生成该角色其他视图，全部以锚点图为参考。
5. 所有角色确认且视图完成后写 character.json，characters done，触发 stage_storyboard。
6. LLM 分集/分段生成 Storyboard，最多两次完整校验；6 秒镜头、未知角色、缺少锚点短语均拦截重试。
7. 每 cut 生成首帧，参考角色锚点；独立记录失败，全部成功后写 storyboard.json 并转 done。
8. 单图 re-generate 只替换该图并重估阶段状态，不触发生成其他图。
9. 已确认锚点被重新生成时，anchor_confirmed 立即失效，其他视图和分镜帧标记 outdated，必须重新确认并重建下游。
10. 阶段重试只补失败/缺失图片，保留已确认锚点和成功图片；只有 CharacterBible/Storyboard 结构化校验失败时才重新调用 LLM。

## API

- GET /api/v1/projects/{id}/characters：设定与图片状态。
- POST /api/v1/projects/{id}/characters/{character_id}/anchor-confirmation：确认锚点并解锁视图。
- POST /api/v1/projects/{id}/character-images/{image_id}/regenerate：单图重生成。
- GET /api/v1/projects/{id}/storyboard：分镜 JSON。
- GET /api/v1/assets/{path}：图片读取。
- 阶段重试扩展 characters/storyboard。

## 前端

项目详情增加大纲、剧本、角色、分镜标签：

- 角色卡显示小传、双语提示词、音色和锚点特征；画廊展示图片状态。
- 未确认 front_full 时显示确认按钮，其他视图锁定；确认后自动刷新。
- 每张失败图可单独重试。
- 分镜横向时间轴按段展开，显示每镜缩略图、时长、运镜和关联台词，点击打开大图。

## 测试与验收

- ImageProvider：提交、上传、轮询、取图、空输出、HTTP 错误和超时，全部 mock。
- Schema：5–8 锚点、cast 覆盖、6 秒 cut、未知角色、缺锚点短语、段超时、非法 line_ref。
- 全流程：FakeLLMProvider + MockImageProvider，锚点确认前无其他视图，确认后完成角色和分镜。
- 单图失败与重试、API 门禁、前端解锁与大图。
- Compose 默认 fake 跑通角色与分镜，另提供本地 ComfyUI/Qwen int8 配置说明。

## 非目标

- 不实现视频生成、场景图、TTS、认证、多租户和生产密钥管理。
- 不要求真实 ComfyUI 才能通过测试或 Mock 验收。
- 不修改 LLMProvider、Outline 或 Script 契约。
