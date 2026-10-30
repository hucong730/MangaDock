# MangaDock

漫坞 MangaDock —— 一部小说进去，一部漫剧出来。开放可插拔的 AI 漫剧流水线：小说 → 剧本 → 角色 → 分镜 → 成片，模型随你接。

MangaDock (漫坞) — One novel in, a comic-drama series out. An open, pluggable pipeline for AI comic-drama production: novel → script → characters → storyboard → video. Bring your own models.

## 当前阶段

阶段三已支持角色设定、参考图与分镜管线：

- 上传 PDF / DOCX / TXT，生成结构化 Outline 和分集 Script，状态与失败原因落库。
- 为角色生成中英提示词、音色和外观锚点；正面全身图经人工确认后才生成其他视图。
- 生成 episode → segment → cut 分镜，机器校验 2–5 秒镜头、角色锚点和完整台词覆盖，并生成每镜关键帧。
- LLM 与图像模型可按项目独立路由；支持 OpenAI 兼容、ComfyUI 和不访问真实服务的 Fake/Mock 实现。
- 前端提供项目进度、Outline/Script、角色卡、锚点确认、单图重试和分镜时间轴。

## 仓库结构

```text
apps/
  api/                 FastAPI HTTP 服务与入队
  worker/              Celery 各阶段任务与图片生成
  web/                 React + Vite + TypeScript 前端
packages/
  core/                解析、schema、Prompt 与生成逻辑
  providers/           LLM/Image 抽象、OpenAI 兼容、ComfyUI 与 Mock 实现
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
curl -X POST http://localhost:8000/api/v1/projects \
  -F 'provider_id=1' \
  -F 'file=@/tmp/mangadock-novel.txt;type=text/plain'

# 3. 替换实际项目 id，轮询状态和资产
curl http://localhost:8000/api/v1/projects/1/status
curl http://localhost:8000/api/v1/projects/1/outline
curl http://localhost:8000/api/v1/projects/1/script
```

前端打开 `http://localhost:5173/projects/1` 可查看时间线、角色、爽点横条和分场剧本。默认 Fake 产出两集合法资产，不访问真实模型。

## 多模型协作配置

Provider 支持 `script`、`image`、`video` 三种能力，缺省为 `script`。每个 Provider 独立配置 `base_url`、`model` 和 `api_key_env`，可以混用不同厂商、网关和密钥。前端“模型 Provider”区域可直接创建多能力 Provider。

示例分别创建三类 Provider（密钥只保存环境变量名）：

```bash
curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"script-pro","base_url":"https://llm.example.com/v1","model":"script-pro","api_key_env":"SCRIPT_API_KEY","capabilities":["script"],"enabled":true}'

curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"image-plus","base_url":"https://image.example.com/v1","model":"image-plus","api_key_env":"IMAGE_API_KEY","capabilities":["image"],"enabled":true}'

curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"video-max","base_url":"https://video.example.com/v1","model":"video-max","api_key_env":"VIDEO_API_KEY","capabilities":["video"],"enabled":true}'
```

创建项目时可分别指定三个 Provider；图像与视频可选，剧本必选：

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -F 'provider_id=1' \
  -F 'image_provider_id=2' \
  -F 'video_provider_id=3' \
  -F 'file=@/tmp/mangadock-novel.txt;type=text/plain'
```

项目详情会显示“剧本 → 图像 → 视频”的模型协作配置。图像 Provider 用于角色参考图和分镜关键帧，视频 Provider 预留给成片阶段。Fake 图像模式允许省略 image 路由；live 图像模式必须配置 ComfyUI Provider。已被引用的 Provider 不能删除、停用或移除使用中的能力。

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
| POST | `/api/v1/projects` | multipart 上传 file 和 provider_id |
| GET | `/api/v1/projects` | 项目列表 |
| GET | `/api/v1/projects/{id}` | 项目详情与 Novel |
| GET | `/api/v1/projects/{id}/status` | 阶段状态和子任务进度 |
| GET | `/api/v1/projects/{id}/outline` | Outline JSON |
| GET | `/api/v1/projects/{id}/script` | Script JSON |
| GET | `/api/v1/projects/{id}/characters` | 角色设定、图片与锚点确认状态 |
| GET | `/api/v1/projects/{id}/storyboard` | 分镜 JSON 与关键帧相对路径 |
| POST | `/api/v1/projects/{id}/characters/{character_id}/anchor-confirmation` | 确认正面全身锚点并解锁其他视图 |
| POST | `/api/v1/projects/{id}/character-images/{image_id}/regenerate` | 单独重生成一张角色图 |
| GET | `/api/v1/assets/{path}` | 读取共享卷内的角色图或关键帧 |
| POST | `/api/v1/projects/{id}/stages/{stage}/retry` | 重试 failed 的 outline、script、characters 或 storyboard |

上传解析错误包括不支持格式、超过 20MB、损坏文件、加密 PDF、空文件、非法 UTF-8 和超长文本。Outline 自动重试一次后仍失败会标记人工处理；前端可手动重试失败阶段。

## 角色与分镜 Mock 验收

默认同时设置 `MANGADOCK_LLM_MODE=fake` 和 `MANGADOCK_IMAGE_MODE=fake`，不需要 ComfyUI。创建项目并等待 Script 完成后：

1. `GET /api/v1/projects/{id}/characters` 查看正面全身锚点图。
2. `POST /api/v1/projects/{id}/characters/{character_id}/anchor-confirmation` 确认锚点，解锁其他视图。
3. 全部角色确认后，角色阶段自动完成并生成分镜。
4. `GET /api/v1/projects/{id}/storyboard` 查看分镜和关键帧；前端角色卡与时间轴可直接查看。
5. 失败图片可用 `POST /api/v1/projects/{id}/character-images/{image_id}/regenerate` 单独重试，不影响其他图片。

## 连接本地 ComfyUI（Qwen Image 2.1 int8）

先启动 ComfyUI 并确认 `http://127.0.0.1:8188/object_info` 可访问。模型文件放在：

```text
ComfyUI/models/diffusion_models/qwen_image_2.1_int8_convrot.safetensors
ComfyUI/models/text_encoders/qwen3vl_8b_int8_convrot.safetensors
ComfyUI/models/vae/qwen_image_2.1_vae_bf16.safetensors
```

在 `.env` 中保留剧本 Mock，同时让图像走真实 ComfyUI：

```dotenv
MANGADOCK_LLM_MODE=fake
MANGADOCK_IMAGE_MODE=live
ASSET_ROOT=/data
COMFYUI_TEMPLATE_DIR=/app/packages/providers/comfyui/templates
COMFYUI_API_KEY=
```

然后创建一个 image 能力 Provider：

```bash
curl -X POST http://localhost:8000/api/v1/llm-providers/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "local-qwen-image",
    "base_url": "http://host.docker.internal:8188",
    "model": "qwen-image-2.1-int8",
    "api_key_env": "COMFYUI_API_KEY",
    "capabilities": ["image"],
    "enabled": true
  }'
```

创建项目时将该 Provider 的 id 传给 `image_provider_id`。`host.docker.internal` 用于 worker 容器访问 Mac 上的 ComfyUI；若在宿主机直接运行 worker，则改用 `http://127.0.0.1:8188`。API Key 环境变量可以为空，模板位于 `packages/providers/comfyui/templates`，可替换工作流而不改业务代码。

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
- [多模型能力路由 ADR](docs/decisions/0003-model-capability-routing.md)
- [角色锚点与分镜 ADR](docs/decisions/0004-character-anchor-storyboard.md)
- [阶段一设计](docs/superpowers/specs/2026-10-30-stage-one-foundation-design.md)
- [阶段二设计](docs/superpowers/specs/2026-10-30-stage-two-novel-script-pipeline-design.md)
- [阶段三设计](docs/superpowers/specs/2026-10-30-character-storyboard-design.md)

## 当前边界

已实现角色参考图和分镜，尚未实现场景图、视频、TTS、认证、多租户和生产级密钥管理。数据库仍使用启动时自动建表，尚未引入 Alembic；20MB 以上或超过字符上限的长小说需要后续分章摘要架构。许可证为 [MIT](LICENSE)。
