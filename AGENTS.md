# MangaDock — Agent Instructions

## 项目简介
模型无关的 AI 漫剧流水线系统：小说(PDF/Word/TXT) → 剧本 → 角色设定 →
分镜 → 成片。所有外部模型（LLM/图像/视频）通过 packages/providers/
下的 Provider 接口接入，业务代码绝不直接调用任何模型 SDK。

## 仓库结构
- apps/api/ — FastAPI 主服务（HTTP 层，不含业务逻辑）
- apps/worker/ — 异步任务执行器（管线各阶段在此运行）
- apps/web/ — React + Vite + TS 前端
- packages/core/ — 管线核心：纯 Python，无框架依赖，必须可单测
- packages/providers/ — OpenAI 兼容 / Anthropic / ComfyUI 等实现
- packages/persistence/ — API 与 worker 共享的 SQLAlchemy 模型与异步 session
- docs/decisions/ — 架构决策记录（ADR）

## 常用命令
- 起全栈：docker compose up
- 后端测试：cd apps/api && pytest
- Worker 测试：cd apps/worker && pytest
- 核心包测试：cd packages/core && pytest
- Provider 测试：cd packages/providers && pytest
- 持久化包测试：cd packages/persistence && pytest
- 前端测试：cd apps/web && npm run test
- 前端构建：cd apps/web && npm run build

## 硬性约定
1. Provider 优先：新接一个模型 = 新增一个 Provider 实现，禁止在
   packages/core 里出现任何厂商 SDK import
2. 管线每阶段输入输出为结构化 JSON（schema 定义在 packages/core/schemas/），
   报告渲染与生成逻辑分离
3. 长任务必须走 worker，禁止在 API 请求线程里同步执行生成
4. 提交信息：英文，Conventional Commits
5. 先写失败测试再实现（TDD）；新功能必须带 pytest 用例
6. 代码与注释用英文；用户可见文案中文为主、英文兜底

## 禁区
- 不要引入 K8s 等重型基础设施（开发机是 16GB Mac）
- 不要在 MVP 阶段实现计费、多租户、TTS
- 不要静默修改 Provider 接口；接口变更必须更新所有现有实现并通知我

## 完成工作的定义
- 测试通过 + docker compose 全栈可起 + 变更摘要写清楚如何本地验证

## Kimi Code 使用约定
- 大功能先进入 Plan 模式给方案，我确认后再执行
- 修改 AGENTS.md 所列目录结构时，必须同步更新本文件
- 权限模式保持默认（需要审批时向我提问，不要 --yolo 绕过）