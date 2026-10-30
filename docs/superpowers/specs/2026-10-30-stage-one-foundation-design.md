# MangaDock 阶段一：仓库骨架与 Provider 基础设施

## 目标与背景

为 MangaDock 搭建最小可运行的 monorepo 基础设施，并建立模型无关的 LLM Provider 边界。本阶段只验证本地开发环境、异步基础设施、配置增删改查和结构化模型输出，不实现任何小说或漫剧生成管线。

## 交付目标

- 按 `AGENTS.md` 创建目录结构，保留现有 Git 历史和 MIT LICENSE。
- 通过一条 Docker Compose 命令启动 FastAPI、Celery、React、PostgreSQL 和 Redis。
- 提供 `/healthz`、SQLAlchemy 异步数据库访问，以及 `llm_providers` 的 API 增删改查。
- 定义 `LLMProvider`，并通过直接 HTTP 请求和 Pydantic 校验实现 OpenAI 兼容 Provider。
- 在简洁的 React 首页显示健康状态和 Provider 数据；由于本阶段已经要求 CRUD API，前端直接接通真实 API。
- 单元测试不连接真实模型、PostgreSQL 或 Redis；随后实际验证 Compose 全栈和 worker 队列。
- 在 README 中说明使用方法，在 `.env.example` 中提供环境变量示例，并用 ADR 记录 Provider 设计决策。

## 非目标与禁止事项

- 不实现小说导入、剧本、角色、分镜、视频或报告生成功能。
- 不实现计费、多租户、TTS、认证、静态加密、自动重试、限流或生产级密钥管理。
- `packages/core` 不导入任何厂商 SDK；API 请求处理函数不调用模型。
- 不引入 Kubernetes、任务工作流框架或额外的 monorepo 构建系统。
- 不能只以单元测试通过作为完成标准，还必须验证 Compose 服务和 Celery 任务实际消费。

## 约束与现状

- 遵循 `AGENTS.md`：API 层保持轻量、core 不依赖框架、使用结构化 schema、长任务只走 worker、采用 TDD、代码与注释使用英文、用户可见文案以中文为主，并遵守 Conventional Commits。
- 仓库已有 `Initial commit`，不重新初始化或改写历史。当前未跟踪的 `AGENTS.md` 会纳入阶段一提交。
- 测试使用 SQLite，Compose 使用 PostgreSQL，Celery 的 broker 和结果后端使用 Redis。
- Docker 镜像必须支持 Apple Silicon，资源占用适合 16 GB Mac。
- 数据库 Provider 记录只保存 `api_key_env`，绝不保存 API Key 的值；API 响应不得泄露密钥。

## 方案选择

### 已选择：直接 HTTP 请求与严格结构化输出

使用 `httpx.AsyncClient` 调用 OpenAI 兼容的 `/chat/completions` 接口。根据调用方提供的 Pydantic 模型生成严格 JSON Schema，通过 `response_format` 请求结构化输出，将返回的消息内容解析为 JSON，再使用原 Pydantic 模型校验。该方案依赖较轻、兼容各类网关，也便于通过 `respx` 编写确定性测试。

备选方案是 OpenAI Python SDK。它能减少少量请求代码，但会引入 SDK 特定行为和耦合，而本阶段没有相应收益。

### 已选择：轻量独立 Python 包

为 `core`、`providers`、`api` 和 `worker` 分别提供包配置，在服务镜像中安装本地包，使用普通的 pytest/npm 命令。不引入 Poetry workspace、Pants、Bazel 或 Nx。

## 具体设计

### 仓库与依赖

- 使用 Python 3.12、FastAPI、SQLAlchemy 异步接口、Pydantic v2、pydantic-settings、httpx、Celery 5、Redis 客户端、asyncpg，以及测试所需的 aiosqlite。
- 前端使用 Vite、React、TypeScript、Vitest 和 Testing Library。
- 根目录包含 `.gitignore`、`.env.example`、`docker-compose.yml`、各服务 Dockerfile 和包配置。
- 保留 `packages/core/schemas/`，但本阶段不添加管线 schema。core 暂无业务行为，因此只做包结构与导入冒烟测试。

### Provider 接口

`LLMProvider` 是抽象基类，包含如下异步泛型方法：

```python
async def chat(
    self,
    messages: Sequence[Mapping[str, str]],
    schema: type[ModelT],
) -> ModelT:
    ...
```

`ModelT` 限定为 `pydantic.BaseModel` 的子类。方法返回调用方所传 schema 的实例。实现必须校验输出，不能返回未经检查的字典。

`OpenAICompatibleProvider.from_env()` 读取 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和 `OPENAI_MODEL`。构造函数允许传入可选参数及 HTTP 客户端，以便隔离测试；应用的标准使用方式仍是从环境变量构造。统一处理 base URL，确保 `/chat/completions` 恰好出现一次。

Provider 按原顺序发送 system/user 消息，请求严格 JSON Schema，检查 HTTP 和响应结构错误，并针对配置、网络传输、上游 API 和无效输出抛出稳定的 Provider 专属异常。本阶段不做静默重试，也不降级为非结构化输出。

### Provider 配置增删改查

REST 路由统一放在 `/api/v1/llm-providers` 下：

- `POST /`：创建记录。
- `GET /`：列出记录。
- `GET /{provider_id}`：获取单条记录。
- `PATCH /{provider_id}`：部分更新可修改字段。
- `DELETE /{provider_id}`：删除记录并返回 204。

字段包括整数 `id`、唯一的 `name`、`base_url`、`model`、`api_key_env`、`enabled`、`created_at` 和 `updated_at`。创建时校验非空字符串和 URL 格式。名称重复返回 409，记录不存在返回 404。API 响应不得读取或返回环境变量中的密钥值。

本阶段的开发骨架由应用启动流程自动建表，暂不引入 Alembic。SQLAlchemy 模型和 session 生命周期放在路由之外，保持路由轻量。测试通过依赖覆盖使用异步 SQLite，并针对真实 SQL 语句验证 CRUD。

### 健康检查与 worker

`GET /healthz` 实际执行 `SELECT 1`，成功时返回 HTTP 200 和 `{"status":"ok","database":"ok"}`。数据库失败时返回 HTTP 503，不能误报健康。

Celery 使用 Redis 作为 broker 和结果后端。提供一个返回 `pong` 的最小 `ping` 任务，用于证明 worker 能启动并消费队列。它不是生成任务，也不引入管线业务。

### Web

首页显示服务健康状态和 Provider 表格，使用中文标签，必要时提供英文兜底。通过 Vite 开发代理和 Compose 网络请求 `/healthz` 与 `/api/v1/llm-providers/`。页面显示加载、空列表和失败状态。本阶段不要求创建表单，CRUD 由 API 测试验收。

### Docker Compose

包含 `api`、`worker`、`web`、`postgres` 和 `redis` 五个服务。PostgreSQL 和 Redis 配置健康检查，并按需使用命名卷。API 和 worker 等待基础设施健康后启动；API 的 FastAPI 服务暴露在 8000 端口，web 的 Vite 服务暴露在 5173 端口。环境变量来自 `.env.example` 的默认值及本地覆盖。仅启动全栈不要求配置真实模型密钥。

### 测试与验证

每个功能切片遵循先写失败测试、再实现、最后重构的 TDD 流程。

- Provider 测试使用 `respx`，覆盖结构化输出成功、环境变量加载、请求 schema 和消息内容、缺少配置、HTTP/API 错误、畸形 JSON、schema 不匹配和上游响应结构错误。
- API 测试覆盖健康检查成功与失败、所有 CRUD 路由，以及输入校验、重名、记录不存在、部分更新和密钥不泄露。
- core 测试只覆盖当前实际存在的包结构。
- worker 测试覆盖任务行为；Compose 验证还会通过 Redis 发送 `ping` 并等待 worker 返回 `pong`。
- Web 测试覆盖健康状态、列表渲染和请求失败，并执行生产构建。
- 执行 `AGENTS.md` 的标准命令，为该文件补充 Provider 测试命令，运行全部测试套件，然后构建并启动 Compose。在当前机器上验证真实 HTTP 响应和 Celery 消费。如果本机缺少 Docker 或其他运行时，明确报告无法验证的部分。

### 文档与提交

扩展 README，加入中英项目描述、架构、前置条件、安装、测试和验证方法。`.env.example` 记录所有 Compose 和 Provider 环境变量，但不包含真实凭据。新增 `docs/decisions/0001-llm-provider-abstraction.md`。如新包需要额外标准命令，同步更新 `AGENTS.md`。最终用一个英文 Conventional Commit 提交已批准的阶段一工作。

## 实现者可自行决定的事项

实现者可决定内部模块名称、具体 Pydantic 请求/响应模型、CSS 细节、依赖补丁版本和测试 fixture。这些决定不得改变公开的 Provider 方法签名、API 密钥策略、必需服务或本阶段范围。
