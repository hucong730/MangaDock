# MangaDock

漫坞 MangaDock —— 一部小说进去，一部漫剧出来。开放可插拔的 AI 漫剧流水线：小说 → 剧本 → 角色 → 分镜 → 成片，模型随你接。

MangaDock (漫坞) — One novel in, a comic-drama series out. An open, pluggable pipeline for AI comic-drama production: novel → script → characters → storyboard → video. Bring your own models.

## 当前阶段

阶段二已支持小说导入和剧本生成管线：

- 上传 PDF / DOCX / TXT，原始文件上限 20MB，统一解析为 Novel。
- 生成结构化 `outline.json` 与 `script.json`，包含角色、爽点节奏、分集分场、动作和台词。
- Celery 执行大纲阶段，按集并行生成剧本；状态、进度和错误落库。
- 前端支持项目上传、进度时间线、Outline/Script 视图和失败阶段重试。
- 阶段一的 Provider 配置 CRUD、健康检查和 PostgreSQL/Redis 基础设施保留。

## 仓库结构

```text
apps/
  api/                 FastAPI HTTP 服务与入队
  worker/              Celery 大纲、逐集生成与汇总
  web/                 React + Vite + TypeScript 前端
packages/
  core/                解析、schema、Prompt 与生成逻辑
  providers/           LLMProvider、OpenAI 兼容与 Fake 实现
  persistence/         共享 SQLAlchemy 模型与异步 session
docs/
  decisions/           架构决策记录
```

## 快速开始（默认 Mock Provider）

前置条件：支持 Apple Silicon 的 Docker Desktop（或等价 Docker 运行时）和 Docker Compose v2。默认 `MANGADOCK_LLM_MODE=fake`，不需要真实 API Key。

```bash
cp .env.example .env
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

## 用 Mock Provider 验证完整流程

先创建一个指向本地示例地址的 Provider。Fake 模式不会向该地址发请求，但项目仍通过 `provider_id` 选择配置，完整解析、schema 校验、队列和数据库路径都会执行。

```bash
# 1. 启动并创建 Provider
curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "fake",
    "base_url": "https://api.example.com/v1",
    "model": "fake-model",
    "api_key_env": "OPENAI_API_KEY",
    "enabled": true
  }'

# 2. 准备小说并上传（将返回的 Provider id 替换到 provider_id）
printf '第一章 归来\n林夏回到旧港。\n第二章 录音\n她听见父亲的声音。' > /tmp/mangadock-novel.txt
curl -X POST http://localhost:8000/projects \
  -F 'provider_id=1' \
  -F 'file=@/tmp/mangadock-novel.txt;type=text/plain'

# 3. 替换实际项目 id，轮询状态和资产
curl http://localhost:8000/projects/1/status
curl http://localhost:8000/projects/1/outline
curl http://localhost:8000/projects/1/script
```

前端打开 `http://localhost:5173/projects/1` 可查看时间线、角色、爽点横条和分场剧本。默认 Fake 产出两集合法资产，不访问真实模型。

## 使用真实模型

在 `.env` 设置：

```dotenv
MANGADOCK_LLM_MODE=live
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-real-key
OPENAI_MODEL=your-model
```

然后重启 worker。数据库只保存 `api_key_env` 的名称，密钥值仅来自 worker 环境变量，不会通过 API 返回。`MANGADOCK_MAX_NOVEL_CHARS` 默认 120000，超出后明确返回 422，不静默截断。

## 项目 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/projects` | multipart 上传 file 和 provider_id |
| GET | `/projects` | 项目列表 |
| GET | `/projects/{id}` | 项目详情与 Novel |
| GET | `/projects/{id}/status` | 阶段状态和子任务进度 |
| GET | `/projects/{id}/outline` | Outline JSON |
| GET | `/projects/{id}/script` | Script JSON |
| POST | `/projects/{id}/stages/{stage}/retry` | 重试 failed 的 outline 或 script |

上传解析错误包括不支持格式、超过 20MB、损坏文件、加密 PDF、空文件、非法 UTF-8 和超长文本。Outline 自动重试一次后仍失败会标记人工处理；前端可手动重试失败阶段。

## 本地测试

本地 Python 测试要求 Python 3.12，前端要求 Node.js 22。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e './packages/providers[test]'
pip install -e './packages/persistence[test]'
pip install -e './packages/core[test]'
pip install -e './apps/api[test]'
pip install -e './apps/worker[test]'

cd packages/persistence && pytest && cd ../..
cd packages/core && pytest && cd ../..
cd packages/providers && pytest && cd ../..
cd apps/api && pytest && cd ../..
cd apps/worker && pytest && cd ../..

cd apps/web
npm ci
npm run test
npm run build
```

OpenAI 兼容测试使用 respx，管线使用 FakeLLMProvider，均不访问真实模型。core 和 providers 的覆盖率门槛均为 100%。

## 设计文档

- [Provider 接口设计 ADR](docs/decisions/0001-llm-provider-abstraction.md)
- [Outline/Script schema ADR](docs/decisions/0002-outline-script-schema.md)
- [阶段一设计](docs/superpowers/specs/2026-10-30-stage-one-foundation-design.md)
- [阶段二设计](docs/superpowers/specs/2026-10-30-stage-two-novel-script-pipeline-design.md)

## 当前边界

尚未实现角色图片、分镜、视频、TTS、认证、多租户和生产级密钥管理。数据库仍使用启动时自动建表，尚未引入 Alembic；20MB 以上或超过字符上限的长小说需要后续分章摘要架构。许可证为 [MIT](LICENSE)。
