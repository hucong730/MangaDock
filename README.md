# MangaDock

漫坞 MangaDock —— 一部小说进去，一部漫剧出来。开放可插拔的 AI 漫剧流水线：小说 → 剧本 → 角色 → 分镜 → 成片，模型随你接。

MangaDock (漫坞) — One novel in, a comic-drama series out. An open, pluggable pipeline for AI comic-drama production: novel → script → characters → storyboard → video. Bring your own models.

## 当前阶段

阶段一提供仓库骨架、Provider 抽象层和本地开发基础设施，尚未实现小说或漫剧生成管线。

- FastAPI `/healthz` 与 `llm_providers` 配置 CRUD
- SQLAlchemy 异步访问 PostgreSQL，测试使用 SQLite
- Celery + Redis worker，以及 `ping → pong` 验证任务
- 模型无关的 `LLMProvider` 与 OpenAI 兼容结构化输出实现
- React + TypeScript 首页，显示健康状态和 Provider 列表
- Docker Compose 一键启动 api、worker、web、postgres、redis

## 仓库结构

```text
apps/
  api/                 FastAPI HTTP 服务
  worker/              Celery 异步任务执行器
  web/                 React + Vite + TypeScript 前端
packages/
  core/                无框架依赖的管线核心（本阶段仅骨架）
  providers/           模型抽象与 OpenAI 兼容实现
docs/
  decisions/           架构决策记录
```

## 快速开始

前置条件：支持 Apple Silicon 的 Docker Desktop（或等价 Docker 运行时）和 Docker Compose v2。仅启动全栈不需要真实模型 API Key。

```bash
cp .env.example .env
# 如需调用真实模型，在 .env 中填写 OPENAI_API_KEY；不要提交该文件。
docker compose up --build
```

打开：

- 前端：http://localhost:5173
- 健康检查：http://localhost:8000/healthz
- API 文档：http://localhost:8000/docs

停止服务：

```bash
docker compose down
# 如需同时删除 PostgreSQL/Redis 数据卷：docker compose down -v
```

## Provider 配置 API

路由前缀：`/api/v1/llm-providers/`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/llm-providers/` | 创建配置 |
| GET | `/api/v1/llm-providers/` | 列出配置 |
| GET | `/api/v1/llm-providers/{id}` | 获取配置 |
| PATCH | `/api/v1/llm-providers/{id}` | 部分更新 |
| DELETE | `/api/v1/llm-providers/{id}` | 删除配置 |

示例：

```bash
curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "primary",
    "base_url": "https://api.openai.com/v1",
    "model": "example-model",
    "api_key_env": "OPENAI_API_KEY",
    "enabled": true
  }'
```

数据库只保存 `api_key_env` 的名称。密钥值只放在环境变量中，不会通过 API 返回。

## 本地测试

本地 Python 测试要求 Python 3.12，前端要求 Node.js 22。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e './packages/core[test]'
pip install -e './packages/providers[test]'
pip install -e './apps/api[test]'
pip install -e './apps/worker[test]'

cd packages/core && pytest && cd ../..
cd packages/providers && pytest && cd ../..
cd apps/api && pytest && cd ../..
cd apps/worker && pytest && cd ../..

cd apps/web
npm ci
npm run test
npm run build
```

Provider 测试使用 respx mock HTTP，不会访问真实模型 API。core 和 providers 的覆盖率门槛均为 100%。

## 全栈验证

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl http://localhost:8000/healthz
curl http://localhost:8000/api/v1/llm-providers/
curl http://localhost:5173/

docker compose exec -T worker python -c \
  'from mangadock_worker.tasks import ping; result = ping.delay(); assert result.get(timeout=15) == "pong"; print("worker: pong")'
```

## 设计文档

- [Provider 接口设计 ADR](docs/decisions/0001-llm-provider-abstraction.md)
- [阶段一设计](docs/superpowers/specs/2026-10-30-stage-one-foundation-design.md)

## 当前边界

本阶段使用应用启动时自动建表，尚未引入数据库迁移、认证、生产级密钥管理、模型重试或业务管线。许可证为 [MIT](LICENSE)。
