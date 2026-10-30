# MangaDock：多模型能力路由与 API 路径修复设计

## 目标

修复前端 `/projects` 与 API 路径冲突，并让项目能够真实配置小说剧本、文生图和视频三个不同 Provider。每个 Provider 可独立使用 base URL、模型名和密钥环境变量，以体现不同优势模型之间的协作。

本阶段只实现配置、校验、持久化和展示，不实现图像或视频生成。

## 已确认方案

### API 命名空间

项目 API 统一使用 `/api/v1/projects`，前端页面保留 `/projects/:id`，避免 Vite 将 API 请求回退为 `index.html`。

### Provider 能力

Provider 可具备 `script`、`image`、`video` 一项或多项能力。缺省能力为 `["script"]`，兼容现有配置。CRUD 校验能力非空、去重且只能包含上述三类。

新增 `provider_capabilities` 表：provider_id、capability，联合唯一，删除 Provider 时级联删除能力记录。使用新表而不是修改旧 llm_providers 表，现有数据库通过 create_all 即可升级。

### 项目模型路由

新增 `project_provider_routes` 表：project_id、role、provider_id，project_id + role 唯一，role 为 script/image/video。

现有 `projects.provider_id` 保留为剧本 Provider，worker 无需改变。创建项目时同时写入三类路由；图像和视频路由可空，剧本路由必选。所有指定 Provider 必须 enabled 且具备对应能力。旧项目没有路由记录时，前端以 provider_id 回退显示剧本模型。

删除 Provider 时同时检查现有 projects.provider_id 和路由表，任一引用存在都返回 409。更新时同样检查两类引用：已被引用的 Provider 不得停用，也不得移除正在使用的能力，否则返回 409；base_url、model 和 api_key_env 可以更新，并只影响后续执行。

## API 与前端

- Provider CRUD 响应增加 `capabilities`；创建/更新接受能力列表。
- 项目创建新增可选 form 字段 `image_provider_id`、`video_provider_id`；现有 `provider_id` 继续表示剧本 Provider。
- 项目响应增加 `provider_routes: [{role, provider_id}]`。
- 前端新增 Provider 创建表单：名称、Base URL、模型、密钥环境变量和能力多选，成功后刷新列表。
- 项目上传表单显示剧本、文生图、视频三个模型选择，按能力过滤；剧本必选，其他可选。
- Provider 列表展示能力标签；项目详情展示“剧本 → 图像 → 视频”的模型协作配置及“后续阶段使用”提示。
- 新增 ADR 0003 记录能力标签与路由表取舍，README 给出三个不同 Provider 的配置示例。

## 测试与验收

- Provider 默认/自定义/非法能力、更新替换、删除引用。
- 三类项目路由保存、能力不匹配、Provider 停用、可选路由为空、旧项目回退。
- 前端 Provider 创建、三组上传字段、能力过滤和协作展示。
- 回归 `/api/v1/projects` 不再返回 HTML，页面 `/projects/:id` 可访问。
- 全量 pytest、前端测试和构建、Compose 重建；用三个不同 base_url/model/api_key_env 的 Provider 创建项目，核对 PostgreSQL 路由和页面，再跑通 Fake 剧本生成。

## 非目标

- 不实现 ImageProvider、VideoProvider 或实际媒体生成。
- 不实现密钥值数据库保存、认证、多租户或 Alembic。
- 不改变阶段一 LLMProvider.chat 接口，不改变现有剧本 worker 的 Provider 选择逻辑。
