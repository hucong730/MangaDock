# ADR 0003：多模型能力标签与项目路由

- 状态：已接受
- 日期：2026-10-30

## 背景

小说剧本、文生图和视频生成具有不同的模型优势与 API 形态。项目需要混用不同厂商、网关、模型和密钥，同时保持阶段一 LLMProvider 与现有剧本 worker 稳定。

## 决策

### 能力标签

Provider 通过 `provider_capabilities` 表声明 script、image、video 一项或多项能力。缺省为 script，兼容旧配置。能力由子表而不是旧表新增列承载，现有数据库可通过 create_all 升级。启动时以幂等 SQL 为没有任何能力记录的旧 Provider 回填 script。

### 项目路由

项目通过 `project_provider_routes` 保存 script/image/video 三类 Provider。剧本继续使用 projects.provider_id，现有 worker 不变；图像与视频路由可空，供后续阶段消费。创建项目时逐项校验 enabled 与能力匹配。

### 引用保护

已被 projects.provider_id 或 project_provider_routes 引用的 Provider 不得删除、停用或移除使用中的能力，统一返回 409。base_url、model 和 api_key_env 可以修改并影响后续执行。项目创建与 Provider 修改/删除通过 `SELECT ... FOR UPDATE` 串行化，多个 Provider 按 id 顺序加锁，避免并发破坏引用约束。

### API 命名空间

项目 API 使用 `/api/v1/projects`，前端页面使用 `/projects/:id`，避免 Vite 将 API 请求回退为 index.html。

## 备选方案

- 为 LLM、图像、视频分别建三套 Provider 表：重复 CRUD 与密钥逻辑，拒绝。
- 在项目和 Provider 旧表直接加列：需要显式迁移，且多能力不如子表自然，暂不采用。
- 只按 Provider 类型过滤而不保存项目路由：无法表达不同项目使用不同模型组合，拒绝。

## 影响

- 图像路由继续由本 ADR 的 project_provider_routes 承载。
- 阶段四起，实际视频后端改由独立 video_providers 与 project_video_routes 承载，以支持厂商专属配置和精确到分镜段的路由；旧 role=video 仅保留兼容展示，不隐式迁移。
- 后续 ImageProvider/VideoProvider 应直接读取对应项目路由，不应重新选择默认模型。
- 修改能力类型或引用规则需同步更新 CRUD、项目创建、前端、测试和本 ADR。
