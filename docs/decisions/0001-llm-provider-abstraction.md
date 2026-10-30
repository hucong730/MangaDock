# ADR 0001：LLM Provider 抽象与 OpenAI 兼容实现

- 状态：已接受
- 日期：2026-10-30

## 背景

MangaDock 需要接入多种模型服务，同时保持管线核心与具体厂商解耦。阶段一需要确定统一的结构化对话接口、OpenAI 兼容服务的调用方式，以及 Provider 配置中密钥的保存边界。

## 决策

在 `packages/providers` 定义抽象基类 `LLMProvider`：

```python
async def chat(
    self,
    messages: Sequence[Mapping[str, str]],
    schema: type[ModelT],
) -> ModelT:
    ...
```

`ModelT` 限定为 Pydantic `BaseModel` 子类。每次调用必须返回调用方所传 schema 的校验后实例，不向业务层返回未经验证的字典。

`OpenAICompatibleProvider` 使用 `httpx.AsyncClient` 直接请求 `{base_url}/chat/completions`。请求通过 `response_format.json_schema` 携带严格 JSON Schema，随后对消息内容执行 JSON 解析和 Pydantic 校验。发送前会递归转换 Pydantic schema：对象设置 `additionalProperties: false`、所有属性列入 `required`，并移除不受支持的 `default` 关键字。Provider 从 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL` 构造。

配置、网络传输、HTTP API 和输出解析错误分别映射为稳定的 Provider 异常。本阶段不重试、不降级为自由文本。

`llm_providers` 数据库表只保存 `api_key_env`，即密钥所在环境变量的名称。数据库和 API 响应均不保存或返回密钥值。

## 备选方案

### OpenAI Python SDK

SDK 可以减少部分请求代码，但会带来额外的 SDK 特定行为和依赖。直接使用 HTTP 更容易覆盖兼容网关，并能用 respx 对接口契约做确定性测试，因此不采用。

### 在数据库中保存 API Key

直接保存密钥便于 CRUD 管理，但需要加密、脱敏和访问控制。当前阶段没有这些安全设施，因此只保存环境变量名。

## 影响

- 新增模型类型时应在 `packages/providers` 增加实现，不得在 `packages/core` 引入厂商 SDK。
- Provider 接口变更必须更新所有实现、测试和本 ADR，并明确通知项目维护者。
- 不支持结构化输出的上游服务需要独立的适配策略，不能静默跳过 Pydantic 校验。
- 当前环境变量方案适合本地 MVP；后续多用户或生产部署需要单独的认证与密钥管理设计。
