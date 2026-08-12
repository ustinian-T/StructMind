# Unified Agent Core Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make FastAPI's `TutorOrchestrator` the single tutor Agent core for Web and uni-app, with one event protocol, true asynchronous token streaming, native tool messages, and enforced round/token/timeout budgets.

**Architecture:** `TurnContext` owns trusted identity, conversation state, mode, model, and budgets. `TutorOrchestrator` turns that context into a native OpenAI message/tool loop through `AsyncModelGateway`, emitting versioned `AgentEvent` envelopes. FastAPI REST, SSE, WebSocket, and the service-authenticated uniCloud proxy all consume that same event iterator; clients never run or duplicate tutor prompts.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, OpenAI Async SDK, asyncio, pytest; uniCloud Node runtime and `uniCloud.httpclient`; browser/uni-app JavaScript.

---

## Task 1: Define the turn and event contracts

**Files:**
- Create: `src/agents/context.py`
- Create: `src/agents/events.py`
- Create: `tests/test_agent_orchestrator.py`

1. Add failing tests that validate `TurnContext` rejects invalid budgets, trims history deterministically, and keeps trusted `user_id` separate from model-visible content.
2. Add failing tests for a versioned event envelope. Every event must expose `protocol`, `type`, `run_id`, `sequence`, and `timestamp`; `delta` uses `content`; tool events use `tool_call_id`, `tool_name`, and structured `arguments` or `result`; terminal events are `done` or `error`.
3. Run `python -m pytest tests/test_agent_orchestrator.py -q` and confirm the imports/contracts fail.
4. Implement `AgentBudget`, `TurnContext`, `AgentEvent`, and an event factory with monotonic sequence numbers.
5. Run the focused tests and confirm green.

## Task 2: Introduce the asynchronous model gateway

**Files:**
- Create: `src/ai/gateway.py`
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `tests/test_agent_orchestrator.py`

1. Add fake-stream tests for progressive text deltas and fragmented native tool-call arguments.
2. Add configuration for `SM_AGENT_MAX_TOOL_ROUNDS`, `SM_AGENT_MAX_OUTPUT_TOKENS`, `SM_AGENT_TIMEOUT_SECONDS`, and `SM_AGENT_MAX_HISTORY_MESSAGES`, with conservative validated defaults.
3. Implement `AsyncModelGateway` using `AsyncOpenAI`, the existing provider/model normalization, existing proxy settings, and an async generator that yields normalized model chunks without blocking the event loop.
4. Accumulate tool-call fragments by index/id and decode JSON only after the model finishes its tool-call turn.
5. Keep the existing synchronous `AIClient` for non-Agent generation/grading code; no Tutor route may call it after migration.
6. Run focused tests.

## Task 3: Implement TutorOrchestrator with native tool messages and budgets

**Files:**
- Create: `src/agents/orchestrator.py`
- Modify: `src/agents/router.py`
- Modify: `src/agents/prompts.py`
- Modify: `src/tools/registry.py`
- Modify: `tests/test_agent_orchestrator.py`

1. Add a test whose fake gateway emits multiple token chunks and assert the orchestrator yields one `delta` event per chunk before `done`.
2. Add a native-tool test: the second model request must contain an assistant message with `tool_calls` followed by a `role=tool` message carrying the matching `tool_call_id`; it must never contain `[工具调用结果]` or a fake user message.
3. Add tests for unknown tool arguments, maximum tool rounds, output-token budget exhaustion, and wall-clock timeout. Each must terminate with a protocol `error` event and never execute excess work.
4. Implement a deterministic rule-first route classifier that does not require the synchronous client. Unknown messages may route to a safe default so token streaming begins immediately.
5. Implement `TutorOrchestrator.stream(context, tool_registry)` as one async state machine: emit `meta`/`route`, call the gateway, emit progressive `delta`, execute authorized tools, append native assistant/tool messages, and repeat within budget.
6. Estimate output tokens conservatively while streaming and use provider usage when available. Wrap the whole turn in `asyncio.timeout`.
7. Keep prompts only in `src/agents/prompts.py`; the orchestrator composes them once from trusted context.
8. Run focused tests.

## Task 4: Make every FastAPI Tutor transport use the orchestrator

**Files:**
- Modify: `src/routes/ai.py`
- Modify: `src/ai/streaming.py`
- Modify: `server.py`
- Create: `tests/test_agent_transports.py`

1. Add transport tests for REST and SSE using a fake orchestrator. Assert both return the exact same ordered event envelopes and that SSE exposes the first `delta` before the fake turn finishes.
2. Add WebSocket contract coverage where practical through FastAPI's test client; otherwise isolate and test the shared turn runner used by WebSocket.
3. Replace `/api/ai/tutor`, `/api/ai/tutor/stream`, `/api/ai/multi-agent/tutor`, `/api/ai/multi-agent/tutor/stream`, and `/ws/tutor` internals with one context builder plus orchestrator iterator.
4. Persist the assembled assistant reply only after a successful `done`. Preserve existing authentication, AI quota checks, conversation ownership, and question-context construction.
5. Make `sse_stream` accept an async event iterator and serialize events without injecting a second incompatible `done` object.
6. Keep compatibility response fields only as derived summaries; `events` is the authoritative protocol for non-streaming calls.
7. Run transport tests and existing security tests.

## Task 5: Add a service-authenticated FastAPI proxy surface for uniCloud

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `src/routes/deps.py`
- Modify: `src/routes/ai.py`
- Modify: `tests/test_agent_transports.py`

1. Add failing tests proving a missing or wrong `X-StructMind-Service-Key` cannot invoke the model and the configured key can.
2. Add a constant-time service credential dependency. Production startup must reject an unset service key when the internal proxy is enabled; test/dev can leave the endpoint disabled.
3. Implement `/api/internal/agent/tutor` as a non-user-facing adapter accepting sanitized external identity, history, question context, and mode. It must build `TurnContext`, invoke the same `TutorOrchestrator`, and return the same `events` protocol.
4. Do not expose user-scoped local database tools through this stateless service route unless a trusted local identity mapping exists.
5. Run focused authentication and transport tests.

## Task 6: Turn uniCloud into a credentialed proxy and remove duplicate tutor prompts

**Files:**
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`
- Modify: `pages/ai/ai.vue`
- Create: `tests/test_unicloud_agent_proxy.cjs`

1. Add Node tests with a fake `uniCloud.httpclient`: the tutor action must call `SM_AGENT_CORE_URL/api/internal/agent/tutor`, send `X-StructMind-Service-Key`, forward mode/history/context, and return the core's unchanged event envelopes.
2. Assert the cloud function has no tutor system prompt and cannot directly call a model for Tutor turns.
3. Implement the proxy after cloud-token validation and conversation ownership checks. Persist the reply assembled from `delta` events, then return `message`, `conversation_id`, and authoritative `events`.
4. Update uni-app to render `delta` events from the shared protocol and retain a message fallback for older deployed cloud functions.
5. Forward `standard` and `multi-agent` as context modes only; both execute in FastAPI.
6. Run all Node tests.

## Task 7: Update the Web adapter and retire duplicate Agent paths

**Files:**
- Modify: `static/app.js`
- Modify: `src/agents/mentor.py`
- Modify: `README.md`
- Modify: `tests/test_agent_transports.py`
- Modify: `tests/test_web_workspace.cjs`

1. Add client contract tests asserting Web consumes `content` from `delta`, honors terminal events, and does not infer a second protocol from `done: true` or bare `delta` fields.
2. Update WebSocket/SSE/REST fallbacks to use the same event reducer.
3. Remove production calls to `run_multi_agent_pipeline`. Keep a short compatibility wrapper only if another tested non-route caller still imports it; it must delegate to the orchestrator or be clearly deprecated and unreachable.
4. Document the protocol, service credential, budget environment variables, and boundary: FastAPI owns Tutor prompts/models/tools; uniCloud owns cloud identity and conversation persistence only.
5. Run focused Web and Python tests.

## Task 8: End-to-end verification

**Files:**
- Verify all modified files.

1. Run `python -m pytest tests -q`.
2. Run every `tests/test_*.cjs` with Node.
3. Run `python -m compileall -q server.py src tests`.
4. Run `git diff --check` and inspect the final task-scoped diff.
5. Run an offline acceptance harness with a deterministic fake streaming gateway, once through the Web REST/SSE adapter and once through the uniCloud proxy fixture. Assert identical protocol/version/type/content order.
6. Record any acceptance item requiring a live provider or deployed uniCloud environment separately; do not claim a live network verification without fresh evidence.
