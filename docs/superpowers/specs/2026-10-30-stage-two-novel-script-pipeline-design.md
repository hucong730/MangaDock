# MangaDock 阶段二：小说导入与剧本生成管线

## 目标与背景

在阶段一的 Provider、服务和密钥边界之上，实现小说上传到结构化大纲与分集剧本的完整闭环。用户可以上传 PDF、DOCX 或 TXT，选择项目 Provider，通过 worker 生成 Outline 和 Script，并在前端查看进度、结果和失败原因。

本阶段复用 `LLMProvider.chat(messages, schema)`，不修改其签名，不在 core 中引入任何厂商 SDK。

## 交付目标

- `POST /projects` 接受不超过 20MB 的 `.pdf`、`.docx`、`.txt` 文件和 `provider_id`，解析为统一 `Novel` 并入库。
- 在 `packages/core/schemas` 定义 Novel、Outline、Script、Episode 及相关 Pydantic 模型和校验器。
- 在 `packages/core/parsing` 实现三种格式解析及损坏、加密、空文件错误分类。
- Celery 链式执行大纲和剧本阶段，剧本按集并行，状态、进度、错误和重试信息落库。
- 提供项目列表、详情、状态、Outline、Script 和阶段重试 API。
- 前端提供项目上传与列表、状态时间线、Outline 角色与爽点视图、Script 阅读视图和阶段重试。
- 通过三种格式 fixture、损坏 PDF、schema 测试和 FakeLLMProvider 全流程测试验收。
- 新增 Outline/Script schema ADR，更新 README 与目录约定。

## 非目标与约束

- 不实现角色图片、分镜、视频、TTS、认证、多租户、计费或生产密钥管理。
- 不修改 Provider 接口，不让 API 请求线程执行 LLM 生成。
- 不引入 Kubernetes、消息队列之外的工作流服务或重型基础设施。
- 继续使用应用启动时 `create_all`；本阶段只新增表，不做既有表的不兼容迁移。
- 代码和注释使用英文，前端及 API 用户可见错误以中文为主，提交使用英文 Conventional Commits。
- 每个功能切片遵循先失败测试、后最小实现的 TDD 流程。

## 方案选择

### 新增共享 persistence 包

新增 `packages/persistence`，集中定义 SQLAlchemy 模型、session 和仓储。API 与 worker 均依赖它，避免 worker 导入 FastAPI 应用，也保持 `packages/core` 无框架依赖。同步更新 `AGENTS.md` 的目录和测试命令。

备选方案是 worker 复用 API 数据库模块或通过内部 HTTP 回调，分别会造成应用包耦合和额外的网络/失败处理复杂度，均不采用。

### Celery chain + chord

上传提交后 API 只通过 Celery `send_task` 入队。worker 先执行 `stage_outline`，成功后启动一个 chord：每个 episode 一个并发生成任务，全部完成后汇总 Script。阶段和 episode 状态独立落库，避免仅以 Celery 结果后端作为业务状态来源。

### 可复现的 Mock 模式

worker 增加 `MANGADOCK_LLM_MODE=fake|live`。`fake` 模式使用实现同一 `LLMProvider` 接口的 `FakeLLMProvider`，根据请求的 schema 返回合法 Outline 或 Episode；`live` 模式按项目 Provider 记录构造 `OpenAICompatibleProvider`。

Compose 默认使用 `fake`，使用户无需真实 API Key 即可验收完整流程；设置为 `live` 时仍严格按项目的 `provider_id`、`base_url`、`model` 和 `api_key_env` 执行。Fake 不绕过 Pydantic 校验，不写入 API 或前端特例。

## 数据契约

### Novel

- `title: str`
- `chapters: list[Chapter]`
- Chapter：`index: int`、`title: str`、`text: str`

标题默认取文件名 stem。按常见“第…章”标题切分；无法识别时生成单个“正文”章节。章节 index 从 1 连续排列，标题和文本不得为空。

### Outline

沿用已审核示例：

- `synopsis: str`
- `cast: list[CastMember]`：`name`、`role`、`weight`（0 到 1）
- `episode_beat: list[EpisodeBeat]`：`episode`、`summary`、`payoff_type`、`payoff_intensity`（1 到 5）
- `asset_list: list[str]`

校验非空文本、角色名唯一、集号从 1 连续、强度范围，以及强度 5 的大爆点间隔不超过 8 集。

### Script

沿用已审核示例：

- `cast: list[CastMember]`：从 Outline 原样快照，支持 Script 自校验。
- `episodes: list[Episode]`
- Episode：`episode`、`estimated_duration_s`、`scenes`
- Scene：`index`、`heading`、`action_beats`、`lines`
- ActionBeat：`order`、`text`
- Line：`order`、`character`、`emotion`、`text`

校验角色归属、集号/场号连续、每场 order 从 1 连续、动作开头且动作与台词严格交替、台词非空。episode 的 `estimated_duration_s` 由 validator 按全部台词中文汉字数重新计算并覆盖，`ceil(汉字数 / 4.5)`；不信任 LLM 提交的时长。零台词时允许 0，负数不可能产生。

Prompt 固定为已审核的 `outline_v1.md` 和 `script_v1.md`，放在 `packages/core/pipeline/prompts`，作为包数据发布。大纲输入完整 Novel，剧本子任务输入完整 Outline 与目标集号，输出单个 Episode，汇总时加入 cast 快照并再次校验完整 Script。

## 文件解析

`parse_novel(filename: str, content: bytes) -> Novel` 按扩展名分派：

- TXT：UTF-8（含 BOM）直读，编码或内容错误给出明确提示。
- PDF：pypdf 逐页提取；加密 PDF 返回“PDF 已加密”，读取/解析异常返回“PDF 文件损坏或无法解析”。
- DOCX：python-docx 读取段落；读取/解析异常返回“Word 文件损坏或无法解析”。
- 三种格式统一在文本清洗后检查空内容，返回“文件未包含可用文本”。

API 对不支持的扩展名返回 415，对超过 20MB 返回 413，对解析失败返回 422 和具体中文原因。只持久化解析后的 Novel JSON、原文件名和媒体类型，不要求保存原始二进制。

## 持久化与 API

### 表

- `projects`：id、title、source_filename、source_media_type、provider_id、novel_json、outline_json、script_json、created_at、updated_at。
- `project_stages`：id、project_id、stage（outline/script）、status（pending/running/done/failed）、completed_items、total_items、attempt_count、requires_attention、error、updated_at。
- `project_episodes`：id、project_id、episode、status、attempt_count、error、payload_json、updated_at，并对 project_id + episode 唯一约束。

`requires_attention` 在大纲两次尝试均失败后设为 true；错误信息保存可读原因，不保存 API Key 或完整敏感请求。

### 路由

- `POST /projects`：multipart 上传 file 和 provider_id；验证 Provider 存在且 enabled；创建项目及阶段记录后入队，返回 201。
- `GET /projects`：项目列表，包含标题、来源、当前阶段状态和创建时间。
- `GET /projects/{id}`：项目详情及 Novel 章节信息。
- `GET /projects/{id}/status`：上传、outline、script 三阶段状态，以及当前 completed/total、错误和是否需要人工处理。
- `GET /projects/{id}/outline`：存在时返回 Outline JSON，未完成返回 409，缺失项目返回 404。
- `GET /projects/{id}/script`：存在时返回 Script JSON，规则同上。
- `POST /projects/{id}/stages/{stage}/retry`：仅允许重试 failed 阶段，返回 202；重置对应资产与进度后重新入队。

Outline 重试会清空下游 Script 与 episode 记录。Script 重试重新生成全部集，保证汇总资产一致；本阶段不做单集选择性重试。

## Worker 行为

- `stage_outline(project_id)`：读取 Novel 与 Provider，最多执行两次完整 LLM + Outline 校验；第一次失败记录并立即进行第二次，第二次失败将阶段设为 failed 和 requires_attention。成功时写入 Outline、建立 episode 记录，然后触发剧本 chord。
- `stage_episode(project_id, episode)`：读取 Outline，生成并校验单集，独立更新 running/done/failed、attempt_count 和 error。失败不会被静默忽略，chord 汇总时将整个 Script 阶段标记 failed。
- `stage_script(project_id)`：作为 chord 回调，确认所有 episode 成功、按集号排序、组装并校验完整 Script，再写资产和 done 状态。
- 任务异常统一转换为持久化失败状态；API 重试创建新任务，不依赖 Celery 隐式重试来猜测业务状态。

## 前端

使用 React Router 增加项目列表和项目详情路由，保留健康状态与 Provider 管理能力。

- 项目列表：上传文件、选择 enabled Provider、展示解析/入队错误及项目状态。
- 详情时间线：上传 → 大纲 → 剧本；pending/running/done/failed 分别显示等待、转圈、打勾和错误。
- 运行阶段每 2 秒轮询 status，显示 `completed/total`；完成后停止轮询并加载对应资产。
- Outline：角色表和按集排列的爽点横条，强度 1-5 映射宽度并突出大爆点。
- Script：分集分场阅读，按合并 order 交替展示动作与台词，角色使用稳定颜色并显示情绪与估算时长。
- 失败：显示后端错误和“重试该阶段”按钮，重试后恢复轮询。

## 测试与验收

- 解析 fixture：小型 TXT、真实 pypdf 生成 PDF、真实 python-docx 生成 DOCX、损坏 PDF；另测加密 PDF、空文件、TXT 编码、扩展名和 20MB 边界。
- Schema：覆盖合法资产及空文本、角色重复、集号/场号、爆点间隔、未知台词角色、交错顺序、时长重算和零台词。
- Core pipeline：FakeLLMProvider 跑通 Novel → Outline → Episodes → Script；用顺序失败的 Fake 验证第一次校验失败、第二次成功，以及两次失败后人工标记。
- API：SQLite 覆盖上传、列表、详情、状态、资产 409/404、重试和入队 mock。
- Worker：覆盖任务状态、并行汇总、单集失败传播、Provider 选择和 fake/live 工厂。
- 前端：上传、状态轮询、三类视图、失败原因和重试按钮。
- 最终运行全部原有及新增测试、前端构建、Compose 五服务。默认 fake 模式实际上传三种格式，轮询至 Script done，检查 API JSON、前端页面和 PostgreSQL 状态；再测试一次失败后手动重试。

## 文档与提交

- 新增 `docs/decisions/0002-outline-script-schema.md`，记录 cast 快照、order 交错、时长重算和爽点校验取舍。
- 更新 `AGENTS.md` 的 persistence 目录和测试命令。
- README 增加上传 API、状态/重试、fake/live 配置和 Mock 全流程验证步骤。
- 最终用英文 Conventional Commit 提交，输出变更摘要、Mock 验证步骤和遗留问题。

## 补充决策与已批准 Prompt

### 边界行为

- 解析后以全部章节 `text` 的字符总数检查 `MANGADOCK_MAX_NOVEL_CHARS`，默认 120,000。超限返回 422，明确提示当前生成字符上限，不创建待生成项目、不入队，也不截断原文。20MB 仍是原始上传文件大小上限。
- 每个 episode 每次阶段执行只调用一次 LLM，不在子任务内自动重试；失败后通过 Script 阶段重试重新生成。`attempt_count` 记录实际执行次数。
- 数据库创建成功但 Celery 入队失败时保留项目，将 Outline 阶段设为 failed、requires_attention=true，并保存“任务入队失败，请重试”错误。`POST /projects` 仍返回 201 和该项目，前端可执行阶段重试，避免重复上传与重复项目。

### `outline_v1.md` 定稿

```text
你是 MangaDock 的漫剧改编主编。你的任务是把输入的 Novel JSON 改编为结构化的 Outline JSON。

工作原则：
1. 忠于原著的核心人物关系、主要冲突和因果链，不随意改变故事真相。
2. 默认采用“抽核”策略：保留主线与高情绪价值事件，合并重复场景，删减不影响主线的支线。
3. 只有输入明确指定 expand 时才采用“扩写”策略；扩写可以补充过渡情节，但不得改变核心设定。
4. 面向短剧表达，每集必须有明确目标、冲突或信息增量，并在结尾形成继续观看的动力。

按以下顺序完成编辑决策：
1. 从全部章节提取候选角色，合并同一角色的别名，区分主角、关键配角和可删减角色。
2. 确定抽核或扩写策略，保留推动主线的角色与事件。
3. 规划全剧爽点节奏。爽点强度使用 1-5 的整数，强度 5 为大爆点；任意两个大爆点之间不得超过 8 集。
4. 逐集编写梗概，并整理后续角色设定与分镜可复用的资产清单。

输出规则：
- 只输出符合调用方 schema 的 Outline JSON，不输出 Markdown、解释或分析过程。
- synopsis 应概括主角、核心冲突和主要悬念。
- cast 必须覆盖后续剧情所需角色；name 为统一角色名，role 同时说明身份和必要的人物关系，weight 为 0 到 1 的戏份权重。
- episode_beat 按 episode 从 1 开始连续排列；summary 是具体事件梗概，不写空泛情绪描述。
- payoff_type 使用简洁中文标签，如“身份反转”“复仇打脸”“危机升级”“情感救赎”。
- asset_list 汇总可复用的角色造型、场景和关键道具，使用简洁中文名称。
- 不输出 schema 未定义的字段。
```

### `script_v1.md` 定稿

```text
你是 MangaDock 的短剧编剧。你的任务是根据输入的完整 Outline JSON 和目标集号，生成该集的 Episode JSON。

创作要求：
1. 忠实呈现目标 episode_beat 的梗概、爽点类型和强度，不擅自改写其他集的剧情。
2. 保持角色身份、人物关系和因果链一致，让场景具有明确动作、冲突和视觉表现。
3. 台词应体现角色差异，情绪标注简洁准确，避免用台词复述动作。
4. 每场结尾推动情节；每集结尾保留与爽点节奏一致的钩子或情绪落点。
5. 只使用 Outline cast 中的角色。不得临时加入旁白、路人或其他未定义角色。

结构与顺序：
- scenes 按 index 从 1 开始连续排列，heading 使用“地点·时间·内/外景”格式。
- action_beats 和 lines 通过 order 共同表示阅读顺序。
- 每场从 order = 1 的动作开始，随后动作与台词严格交替；order 连续且不重复。
- action_beats 只包含可表演或可拍摄的动作，不包含角色台词。
- lines 的 character 必须逐字匹配 cast 中的 name，emotion 为简短中文情绪标注。
- estimated_duration_s 按本集全部台词中的中文汉字数计算：ceil(汉字数 / 4.5)。标点、空格、动作和场景标题不计时。

输出规则：
- 只输出目标集的 Episode JSON，不输出完整 Script，不输出 Markdown、解释或分析过程。
- 输出字段仅限 episode、estimated_duration_s、scenes，以及 schema 规定的场景、动作和台词字段。
- 不输出 schema 未定义的字段。
```

## 实现者可自行决定的事项

内部模块拆分、仓储函数名称、fixture 辅助函数、前端组件与 CSS 细节可由实现者决定，但不得改变已确认的 JSON 字段、Provider 签名、Prompt v1 内容、路由语义、Mock 校验路径或本阶段范围。
