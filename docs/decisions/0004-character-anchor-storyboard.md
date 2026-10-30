# ADR 0004：角色锚点、分镜硬门与 ComfyUI 模板

- 状态：已接受
- 日期：2026-10-30

## 背景

连续角色形象是多镜头漫剧一致性的基础。直接为每镜独立生成角色容易漂移，短剧节奏也需要明确机器可校验的约束，而不是依赖模型自觉遵守。

## 决策

### 先锚点、后视图、再分镜

每角色先生成正面全身锚点图，人工确认后才允许生成头像、侧脸、背面和服装细节。后续视图只能引用已确认锚点。重新生成已确认锚点会使确认、下游图片和已有分镜关键帧失效，避免未审核的新身份被沿用。单图失败只影响该图并可独立重试。

多角色同镜最多传入四张锚点图，保持 image_1…4 与角色顺序一致；prompt 中的 <imageN>角色名</imageN> 也由脚本校验顺序。scene_ref 留待阶段四。

### cuts 2–5 秒、segments 不超过 15 秒

2–5 秒足够表达一个动作或一句台词，同时避免静态镜头过长。段时长由 cuts 重算并限制为 15 秒，便于后续视频拼接与节奏控制。所有 Script 集和全部台词按原顺序恰好出现一次，防止模型省略剧情。

角色名必须属于 cast，每镜 prompt 必须包含该角色至少一条锚点特征短语。校验在代码执行，未知角色、缺短语、超时时长和遗漏/重排/复用台词均不能通过。

### Provider 与模板耦合

ImageProvider 只关心 prompt、参考图和尺寸。Qwen 特有节点、模型文件和采样参数全部封装在 ComfyUI 工作流模板中，按 character_anchor_v1、character_views_v1、storyboard_keyframe_v1 管理。模板通过 /upload/image 接入参考图，/prompt 提交，/history 轮询，/view 下载。

复用 llm_providers 的 image 能力和项目路由，不复制 image_providers 配置表。MANGADOCK_IMAGE_MODE 可独立覆盖 MANGADOCK_LLM_MODE，允许剧本用 Fake、图像用真实 ComfyUI。

## 影响

- 角色设定、关键帧和视频阶段共享同一锚点来源，减少跨阶段漂移。
- 修改锚点或时长规则需要同步 schema、Prompt、worker、前端和本 ADR。
- Mock 与真实后端必须经过相同资产校验，不允许绕过人工确认或时长硬门。
