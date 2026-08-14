# uniCloud 用户级五模型配置设计

日期：2026-08-14
状态：已批准（方案 A）

## 1. 背景与结论

StructMind 当前只有一个面向用户的运行端：部署在 uniCloud 的电脑 Web 端。FastAPI 不再被视为另一套用户端，只作为 uniCloud 调用的内部 Agent 核心。

现有 AI 配置存在两处全局状态：

- uniCloud `structmind-ai` 云函数使用 `SM_AI_API_URL`、`SM_AI_API_KEY` 和 `SM_AI_MODEL`，所有用户共享一份密钥。
- FastAPI 使用进程级 `RUNTIME_CONFIG`，配置接口仅管理员可写，所有用户共享一份密钥。

这两种方式都不符合“每个用户独立填写 API Key、独立选择模型”的产品要求。本设计确定由 uniCloud 成为唯一的用户 AI 配置权威源，所有 AI 功能统一解析当前登录用户的配置；FastAPI Agent 核心只在单次调用中使用短期加密凭据，不持久化终端用户密钥。

## 2. 目标

1. 为每个已批准用户提供独立的 AI 服务商密钥配置。
2. 固定提供五个模型选项，并阻止任意 Base URL、任意模型名进入调用链。
3. 同一份用户配置覆盖 AI 导师、题目讲解、变式出题、作业评分和讨论题评分。
4. API Key 加密存储、响应脱敏、日志不可见、用户间严格隔离。
5. uniCloud 负责用户鉴权和配置权威；FastAPI 仅承担内部 Agent 编排。
6. 保持现有学习记录、对话记录和 Agent 事件协议兼容。

## 3. 非目标

- 不把用户提供的 API Key 写入源码、仓库、构建产物或测试夹具。
- 不允许用户填写自定义 Base URL，避免 SSRF 和凭据外传。
- 不保留管理员替所有用户配置全局密钥的前端入口。
- 不把浏览器 `localStorage` 作为密钥持久化位置。
- 不在本阶段增加新的模型或自动回退到未获用户授权的平台。

## 4. 固定模型目录

模型目录由服务端代码维护，前端只能读取，不能修改端点或协议。

| provider_id | 服务商 | model_id | 协议 | Base URL |
| --- | --- | --- | --- | --- |
| `minimax` | MiniMax | `MiniMax-M3[1M]` | Anthropic Messages | `https://api.minimaxi.com/anthropic` |
| `deepseek` | DeepSeek | `deepseek-v4-flash` | Anthropic Messages | `https://api.deepseek.com/anthropic` |
| `deepseek` | DeepSeek | `deepseek-v4-pro[1m]` | Anthropic Messages | `https://api.deepseek.com/anthropic` |
| `volcengine` | 火山方舟 | `ark-code-latest` | Anthropic Messages | `https://ark.cn-beijing.volces.com/api/plan` |
| `stepfun` | 阶跃星辰 | `step-router-v1` | OpenAI Chat Completions | `https://api.stepfun.com/step_plan/v1` |

MiniMax、DeepSeek 和火山方舟的 Messages 适配器规范化为 `/v1/messages`；StepFun 适配器规范化为 `/chat/completions`。每个目录项还包含认证头策略、超时上限、是否支持流式响应和工具调用能力。

用户给出的模型标识和套餐端点按白名单接入，但不能仅凭保存成功认定模型可用。设置页必须提供连接测试，以识别账户权限、套餐地址或模型标识变动。

## 5. 数据模型

新增 uniCloud 集合 `structmind_user_ai_configs`，每个 `user_id` 最多一条记录：

```text
_id
user_id                  unique
default_model
credentials              object
  minimax                 encrypted credential or absent
  deepseek                encrypted credential or absent
  volcengine              encrypted credential or absent
  stepfun                 encrypted credential or absent
last_tests               object keyed by provider_id
created_at
updated_at
```

每个平台的加密凭据仅包含：

```text
ciphertext
iv
auth_tag
key_version
key_last4
updated_at
```

集合禁止客户端直接读写；所有权限设为 `false`，只允许云函数以服务端身份访问。云函数根据当前 session 的 `user_id` 查询，不能接受前端传入的目标用户 ID。

## 6. 密钥保护

### 6.1 静态存储

- 使用 AES-256-GCM 加密用户 API Key。
- 主密钥来自云函数环境变量 `SM_USER_AI_MASTER_KEY`，要求 Base64 编码的 32 字节随机值。
- AAD 包含 `user_id`、`provider_id` 和 `key_version`，防止密文跨用户或跨服务商替换。
- 每次保存生成新的 96-bit IV。
- 明文只存在于当前云函数调用内存中，用后不写日志。
- 读取接口只返回 `configured`、`key_last4`、更新时间和最近测试状态。

### 6.2 uniCloud 到 Agent 核心

AI 导师需要 FastAPI 执行多智能体编排。uniCloud 解密用户密钥后，不以明文 JSON 字段转发，而是创建短期凭据封套：

```text
provider_id
model_id
api_key
external_user_id
issued_at
expires_at             no more than 60 seconds
nonce
```

封套使用独立环境变量 `SM_AGENT_CREDENTIAL_KEY` 进行 AES-256-GCM 加密。FastAPI 解密后校验有效期、用户 ID、服务商和模型白名单，只在本次 Agent turn 内构造模型网关。原有 `X-StructMind-Service-Key` 继续用于服务身份验证，两道校验均通过才允许调用。

FastAPI 不缓存、不持久化、不回传用户 API Key，也不记录请求体或解密异常中的密文内容。

## 7. 云函数接口

在用户登录后提供以下 `structmind-ai` actions：

### `getAIConfig`

返回模型目录、默认模型和各服务商脱敏状态。未登录或未获批准用户拒绝访问。

### `saveAIConfig`

输入 `provider_id`、`api_key` 和可选 `model_id`。服务端校验白名单、加密并原子更新当前用户记录。空字符串不能覆盖已有密钥。

### `selectAIModel`

输入 `model_id`。只有对应服务商已配置密钥时才能选为默认模型。

### `testAIConnection`

输入 `provider_id` 和可选 `model_id`，使用已保存密钥发起小型非流式请求，限制输出长度。返回规范化状态，不返回供应商原始响应体或任何密钥片段。

### `deleteAIConfig`

删除当前用户指定服务商的加密凭据。若删除的是默认模型所属服务商，清空默认模型并要求用户重新选择，不自动切换到其他已配置平台。

## 8. 统一模型解析

所有 AI action 必须通过同一个解析器取得调用上下文：

```text
resolveUserModel(userId, requestedModel?)
  -> validate model allowlist
  -> load current user's config
  -> choose requested or default model
  -> verify matching provider is configured
  -> decrypt provider key
  -> return ephemeral ModelCredential
```

前端传入的 `model` 只是用户在白名单中的选择，不能携带端点、协议、请求头或 API Key。

下列功能统一改用该解析器：

- `generateQuestion`
- 题目讲解与追问
- `gradeAssignment`
- `gradeDiscussion`
- `tutor` / 多智能体导师

## 9. 协议适配器

uniCloud 模型网关提供统一接口：

```text
callModel({ credential, messages, tools, temperature, maxTokens, stream })
```

内部根据目录选择 Anthropic Messages 或 OpenAI Chat Completions 适配器，并统一输出：

```text
content
tool_calls
usage.input_tokens
usage.output_tokens
finish_reason
provider_id
model_id
```

结构化任务继续由业务层验证 JSON，不信任模型直接返回的数据。工具调用不被服务商支持时，Agent 核心允许降级为无工具对话，但必须给出可理解的功能限制提示。

## 10. 前端设置页

电脑 Web 的“AI 配置”改为“我的 AI 模型”，仅登录用户可用：

- 展示五个模型卡片和四个平台配置状态。
- 每个平台独立输入 API Key，支持显示/隐藏、保存、测试连接和删除。
- 密钥输入框永不回填已保存明文，只显示脱敏尾号。
- 未配置对应平台时，模型选择按钮禁用并提示先配置密钥。
- 当前默认模型在 AI 导师、题目讲解、变式出题、作业评分和讨论题评分入口保持一致。
- 切换模型后刷新页面仍从服务端恢复，不依赖浏览器缓存。
- 明确提示 API Key 仅用于当前账号的 AI 请求。

原有管理员全局配置表单和 `/api/config` 写密钥路径从用户界面移除。FastAPI 可保留环境变量配置作为开发与运维兼容路径，但用户请求不得再读取进程级 `RUNTIME_CONFIG`。

## 11. 错误与状态

统一错误码至少包括：

- `AI_CONFIG_REQUIRED`
- `AI_MODEL_NOT_ALLOWED`
- `AI_PROVIDER_NOT_CONFIGURED`
- `AI_CREDENTIAL_INVALID`
- `AI_QUOTA_EXCEEDED`
- `AI_PROVIDER_TIMEOUT`
- `AI_PROVIDER_UNAVAILABLE`
- `AI_AGENT_PROXY_UNAVAILABLE`

返回给用户的消息不得包含完整上游响应、请求头、密文、API Key 或内部服务地址。连接测试记录只保存错误分类和时间，不保存上游原始错误体。

## 12. 兼容与迁移

1. 新集合上线后，现有用户默认处于未配置状态。
2. 不迁移任何全局 `SM_AI_API_KEY` 或 FastAPI 运行时密钥到个人账户。
3. 用户未配置时，所有 AI 入口展示明确引导；非 AI 的题库和学习功能继续可用。
4. 对话和学习记录的数据结构保持不变，仅新增实际使用的 `provider_id` 和 `model_id` 元数据。
5. 旧全局配置可暂时保留为运维回滚开关，但生产用户调用默认关闭，且前端不可见。

## 13. 测试与验收

### 安全测试

- 用户 A 不能读取、修改或使用用户 B 的配置。
- 配置 GET、错误响应和日志中不存在明文密钥。
- 数据库只保存 AES-GCM 密文、IV、Tag 和尾号。
- 篡改 user ID、provider ID、密文、AAD、有效期或 nonce 时拒绝调用。
- 自定义 URL、未知模型和跨平台模型组合被拒绝。

### 功能测试

- 四个平台密钥可独立保存、测试和删除。
- 五个模型均可被选择，DeepSeek 两个模型共用一份密钥。
- 默认模型刷新后保持一致。
- AI 导师、讲解、变式出题、作业评分和讨论题评分均使用当前用户模型。
- 普通与多智能体导师保持 `structmind.agent.v1` 事件协议。

### 故障测试

- 错误密钥、额度不足、模型无权限、限流、超时、上游 5xx 和 Agent 核心不可用均返回稳定错误分类。
- 删除默认模型凭据后，AI 功能停止并提示重新配置，不静默切换到其他供应商。

### 部署验收

- uniCloud 数据库 schema 和索引部署成功。
- 云函数环境变量缺失时启动失败或明确返回 503，不能退化为明文存储。
- 构建产物不包含真实 API Key、主密钥或服务凭据。
- 生产域名登录后可完成配置、连接测试、模型切换和五类 AI 功能冒烟测试。

## 14. 实施顺序

1. 先写用户隔离、加密和模型解析失败测试。
2. 实现模型目录、加密存储和用户配置 actions。
3. 实现 uniCloud 双协议模型网关并迁移非 Agent AI 功能。
4. 实现短期凭据封套和 FastAPI 临时用户网关。
5. 改造电脑 Web 设置页及全部 AI 入口。
6. 完成单元、集成、构建、密钥扫描和生产冒烟验证。
