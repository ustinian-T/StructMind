# uniCloud User AI Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure per-user API-key configuration for five allowlisted models and route every uniCloud Web AI feature through the selected user model while keeping FastAPI as a credential-ephemeral Agent core.

**Architecture:** uniCloud is the only user-facing configuration authority. The `structmind-ai` cloud function stores AES-256-GCM encrypted provider keys, resolves the authenticated user's model, and either calls an allowlisted provider adapter or sends a 60-second encrypted credential envelope to the internal FastAPI Agent endpoint. The browser receives only catalog metadata and masked key state.

**Tech Stack:** uni-app / Vue, uniCloud Aliyun cloud functions and database schemas, Node.js `crypto` and `node:test`, FastAPI, Pydantic, Python `cryptography` or AES-GCM-compatible standard dependency, pytest.

## Global Constraints

- The only user-facing runtime is the uniCloud-hosted desktop Web app; FastAPI is an internal Agent core, not a second user configuration surface.
- The exact five model IDs are `MiniMax-M3[1M]`, `deepseek-v4-flash`, `deepseek-v4-pro[1m]`, `ark-code-latest`, and `step-router-v1`.
- Provider endpoints and protocols are server-owned allowlist metadata; never accept a user-supplied Base URL.
- Store one independent credential per user and provider; DeepSeek's two models share one DeepSeek key.
- Never write real API keys, encryption keys, or pasted credentials to source, fixtures, logs, responses, screenshots, or build artifacts.
- User API keys must be encrypted with AES-256-GCM under `SM_USER_AI_MASTER_KEY`; Agent envelopes use a separate `SM_AGENT_CREDENTIAL_KEY` and expire in at most 60 seconds.
- Preserve `structmind.agent.v1` responses and existing learning/conversation records.
- Do not migrate global `SM_AI_API_KEY` or FastAPI runtime keys into a user record.
- The worktree is already dirty; preserve unrelated changes and do not stage or commit unless the user explicitly authorizes it.

---

## File Map

**Create**

- `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/provider-catalog.js` — immutable four-provider/five-model allowlist and lookup helpers.
- `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/credential-crypto.js` — AES-GCM user-key encryption and Agent envelope creation.
- `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/user-ai-config.js` — per-user repository, masked payloads, model resolution, configuration actions.
- `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/model-gateway.js` — Anthropic/OpenAI request adapters and normalized errors/results.
- `uniCloud-aliyun/database/structmind_user_ai_configs.schema.json` — server-only user configuration collection.
- `pages/ai-settings/ai-settings.vue` — desktop Web “我的 AI 模型” page.
- `src/ai/credential_envelope.py` — decrypt and validate uniCloud Agent credential envelopes.
- `tests/test_unicloud_user_ai_config.cjs` — catalog, encryption, isolation, CRUD, masking, and selection tests.
- `tests/test_unicloud_model_gateway.cjs` — protocol adapters and error normalization tests.
- `tests/test_agent_user_credentials.py` — envelope validation and ephemeral gateway tests.

**Modify**

- `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js` — use user configuration for all AI actions and create Agent envelopes.
- `uniCloud-aliyun/cloudfunctions/api/index.js` — make legacy `/config` and AI adapter routes call the same user-level cloud actions; split assignment grading from discussion grading.
- `src/config.py` — add environment names and allowlisted provider metadata needed by the internal Agent core, without user keys.
- `src/models/schemas.py` — add the encrypted envelope to `AgentServiceTutorRequest`.
- `src/ai/gateway.py` — allow an explicit ephemeral credential and support Anthropic-compatible Agent streaming.
- `src/routes/ai.py` — decrypt the envelope for `/internal/agent/tutor` and inject the resulting gateway.
- `pages.json` — register `pages/ai-settings/ai-settings`.
- `pages/ai/ai.vue` — show selected model, link to settings, and forward the model selection implicitly through server resolution.
- `pages/profile/profile.vue` — add the “我的 AI 模型” entry.
- `utils/cloud.js` — preserve structured cloud error codes for actionable UI states.
- `tests/test_unicloud_agent_proxy.cjs` — assert encrypted envelope forwarding and no plaintext credential.
- `tests/test_unicloud_ai_permissions.cjs` — remove global-key assumptions and seed per-user encrypted configuration.
- `tests/test_unicloud_frontend.cjs` — assert settings page routing and absence of browser key persistence.
- `.env.example` — document variable names only, with generated-placeholder instructions and no secrets.
- `README.md` — document deployment prerequisites and the user configuration flow.

---

### Task 1: Provider Catalog and Key Cryptography

**Files:**
- Create: `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/provider-catalog.js`
- Create: `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/credential-crypto.js`
- Create: `tests/test_unicloud_user_ai_config.cjs`

**Interfaces:**
- Produces: `listProviders()`, `getProvider(providerId)`, `getModel(modelId)`, `providerForModel(modelId)`.
- Produces: `encryptUserKey(apiKey, { userId, providerId, masterKey, keyVersion })`, `decryptUserKey(record, context)`, `createAgentEnvelope(payload, transportKey)`, and masked `credentialPreview(record)`.

- [ ] **Step 1: Write failing catalog tests**

```js
test('catalog exposes exactly four providers and five fixed models', () => {
  const providers = catalog.listProviders()
  assert.deepEqual(providers.flatMap(item => item.models.map(model => model.id)), [
    'MiniMax-M3[1M]', 'deepseek-v4-flash', 'deepseek-v4-pro[1m]',
    'ark-code-latest', 'step-router-v1',
  ])
  assert.throws(() => catalog.getModel('custom-model'), /AI_MODEL_NOT_ALLOWED/)
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test tests/test_unicloud_user_ai_config.cjs`
Expected: FAIL because the catalog module does not exist.

- [ ] **Step 3: Implement the immutable catalog**

Use frozen records with `provider_id`, `label`, `protocol`, `base_url`, `auth_style`, `models`, `default_model`, `timeout_ms`, and `supports_tools`. Lookup helpers must throw an error carrying `code = 'AI_MODEL_NOT_ALLOWED'` or `code = 'AI_PROVIDER_NOT_CONFIGURED'`; they must never accept a URL argument.

- [ ] **Step 4: Add failing AES-GCM round-trip and tamper tests**

```js
test('encrypted user key is bound to user and provider', () => {
  const masterKey = Buffer.alloc(32, 7).toString('base64')
  const encrypted = encryptUserKey('unit-test-secret', {
    userId: 'user-a', providerId: 'deepseek', masterKey, keyVersion: 1,
  })
  assert.equal(JSON.stringify(encrypted).includes('unit-test-secret'), false)
  assert.equal(decryptUserKey(encrypted, {
    userId: 'user-a', providerId: 'deepseek', masterKey,
  }), 'unit-test-secret')
  assert.throws(() => decryptUserKey(encrypted, {
    userId: 'user-b', providerId: 'deepseek', masterKey,
  }), /AI_CREDENTIAL_INVALID/)
})
```

- [ ] **Step 5: Implement encryption and envelope helpers**

Decode environment keys as exactly 32 bytes, use `aes-256-gcm`, 12-byte random IVs, 16-byte tags, and AAD `${userId}:${providerId}:${keyVersion}`. The envelope payload must include `issued_at`, `expires_at`, `nonce`, `external_user_id`, `provider_id`, `model_id`, and `api_key`; reject any TTL above 60 seconds before encrypting.

- [ ] **Step 6: Run focused tests and inspect the diff**

Run: `node --test tests/test_unicloud_user_ai_config.cjs`
Expected: PASS.
Run: `git diff --check -- uniCloud-aliyun/cloudfunctions/structmind-ai/lib tests/test_unicloud_user_ai_config.cjs`
Expected: no output.

---

### Task 2: Server-Only User Configuration Repository and Actions

**Files:**
- Create: `uniCloud-aliyun/database/structmind_user_ai_configs.schema.json`
- Create: `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/user-ai-config.js`
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`
- Modify: `tests/test_unicloud_user_ai_config.cjs`

**Interfaces:**
- Consumes: catalog and crypto helpers from Task 1.
- Produces: `createUserAIConfigService({ collection, masterKey, now })` with `getPublicConfig(userId)`, `saveCredential(userId, providerId, apiKey, modelId)`, `selectModel(userId, modelId)`, `deleteCredential(userId, providerId)`, `recordConnectionTest(userId, providerId, result)`, and `resolveUserModel(userId, requestedModel)`.

- [ ] **Step 1: Write failing user-isolation and masking tests**

Seed two users and assert that `getAIConfig`, `saveAIConfig`, `selectAIModel`, and `deleteAIConfig` derive the target from the validated session. Add an attempted `params.user_id = 'user-b'` and prove it cannot alter user B.

```js
assert.equal(result.data.providers.deepseek.configured, true)
assert.equal(JSON.stringify(result).includes('unit-test-secret'), false)
assert.equal(tables.structmind_user_ai_configs[0].user_id, 'user-a')
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test tests/test_unicloud_user_ai_config.cjs`
Expected: FAIL because the collection and actions are absent.

- [ ] **Step 3: Add the uniCloud schema**

Set all direct permissions to `false`, define `user_id`, `default_model`, `credentials`, `last_tests`, `created_at`, and `updated_at`, and add a unique index on `user_id`. Do not expose the collection through JQL.

- [ ] **Step 4: Implement repository operations**

Use one record per user. Updates must preserve credentials for other providers, reject blank replacement keys, clear `default_model` when its provider is deleted, and never auto-select another provider. `getPublicConfig` returns the full model catalog plus only `configured`, `key_last4`, `updated_at`, and `last_test` per provider.

- [ ] **Step 5: Wire five authenticated configuration actions**

In `structmind-ai/index.js`, call `requireAuth(params.token)` first for `getAIConfig`, `saveAIConfig`, `selectAIModel`, `testAIConnection`, and `deleteAIConfig`. Configuration actions must return stable `{ code, message, data }` shapes and reject missing `SM_USER_AI_MASTER_KEY` with `AI_CONFIG_REQUIRED`, never with a plaintext-storage fallback.

- [ ] **Step 6: Run tests and verify schema safety**

Run: `node --test tests/test_unicloud_user_ai_config.cjs`
Expected: PASS.
Run: `Select-String -Path uniCloud-aliyun/database/structmind_user_ai_configs.schema.json -Pattern '"read": false|"create": false|"update": false|"delete": false'`
Expected: four matches.

---

### Task 3: Unified Anthropic and OpenAI Provider Gateway

**Files:**
- Create: `uniCloud-aliyun/cloudfunctions/structmind-ai/lib/model-gateway.js`
- Create: `tests/test_unicloud_model_gateway.cjs`
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`

**Interfaces:**
- Consumes: `ModelCredential = { provider_id, model_id, api_key, protocol, base_url, auth_style }` from `resolveUserModel`.
- Produces: `callModel({ httpclient, credential, messages, tools, temperature, maxTokens, stream }) -> { content, tool_calls, usage, finish_reason, provider_id, model_id }`.
- Produces: normalized errors with public codes and redacted messages.

- [ ] **Step 1: Write failing request-shape tests**

Test exact resolved URLs and bodies without using real network calls:

```js
assert.equal(request.url, 'https://api.minimaxi.com/anthropic/v1/messages')
assert.equal(request.body.model, 'MiniMax-M3[1M]')
assert.equal(request.url, 'https://api.stepfun.com/step_plan/v1/chat/completions')
assert.equal(request.body.model, 'step-router-v1')
```

Also test DeepSeek, Volcengine, content-block parsing, OpenAI choices parsing, token usage mapping, timeout, 401/403, 429, and 5xx redaction.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test tests/test_unicloud_model_gateway.cjs`
Expected: FAIL because the gateway module does not exist.

- [ ] **Step 3: Implement protocol adapters**

Anthropic requests separate the system message from user/assistant messages, send `max_tokens`, and extract only visible `text` blocks. OpenAI requests retain the current `messages` shape. Both adapters clamp timeouts and token limits, set only the catalog-defined authentication headers, and never include API keys in thrown messages.

- [ ] **Step 4: Implement safe error normalization**

Map upstream authentication to `AI_CREDENTIAL_INVALID`, quota/429 to `AI_QUOTA_EXCEEDED`, timeout to `AI_PROVIDER_TIMEOUT`, and all other upstream failures to `AI_PROVIDER_UNAVAILABLE`. Preserve only provider label, HTTP status category, and retry guidance.

- [ ] **Step 5: Connect `testAIConnection` to the gateway**

Resolve the saved credential, call a fixed Chinese ping prompt with `maxTokens: 16`, store only `{ ok, code, tested_at, model_id }`, and return the same safe status. Do not store provider content or raw errors.

- [ ] **Step 6: Run focused tests**

Run: `node --test tests/test_unicloud_model_gateway.cjs tests/test_unicloud_user_ai_config.cjs`
Expected: PASS.

---

### Task 4: Route Every Non-Agent AI Feature Through the User Model

**Files:**
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`
- Modify: `uniCloud-aliyun/cloudfunctions/api/index.js`
- Modify: `tests/test_unicloud_ai_permissions.cjs`
- Create: `tests/test_unicloud_ai_routing.cjs`

**Interfaces:**
- Consumes: `resolveUserModel(userId, requestedModel)` and `callModel(...)`.
- Produces: user-routed `generateQuestion`, `questionAI`, `gradeAssignment`, and `gradeDiscussion` actions with `provider_id` and `model_id` response metadata.

- [ ] **Step 1: Write failing routing tests**

For two users configured with different providers, call each action and assert the captured HTTP request uses only that user's endpoint and model. Include a cross-user requested model, unknown model, and missing-provider credential case.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test tests/test_unicloud_ai_routing.cjs tests/test_unicloud_ai_permissions.cjs`
Expected: FAIL because current actions use global `SM_AI_API_KEY` and `SM_AI_MODEL`.

- [ ] **Step 3: Replace the global `callAI` path**

For each action, authenticate first, call `resolveUserModel(userId, params.model)`, then call the shared gateway. Remove production reads of `SM_AI_API_URL`, `SM_AI_API_KEY`, and `SM_AI_MODEL` from user requests.

- [ ] **Step 4: Add dedicated `questionAI` and `gradeAssignment` actions**

`questionAI` accepts an authenticated question ID, mode, and optional follow-up message; it loads server-side question content. `gradeAssignment` accepts an assignment ID and answer; it loads the assignment and returns the same normalized feedback structure expected by the existing Web adapter. Neither accepts reference answers or prompts directly from the browser.

- [ ] **Step 5: Fix the uniCloud `api` compatibility adapter**

Forward `/config` GET/POST to the user-level actions with the bearer token, forward `/assignment/grade` to `gradeAssignment`, and add `/question/ai`. Delete environment-key previews and the accidental assignment-to-discussion forwarding.

- [ ] **Step 6: Run routing and regression tests**

Run: `node --test tests/test_unicloud_ai_routing.cjs tests/test_unicloud_ai_permissions.cjs tests/test_unicloud_regressions.cjs`
Expected: PASS.

---

### Task 5: Encrypted Agent Credential Envelope and Ephemeral FastAPI Gateway

**Files:**
- Modify: `tests/test_unicloud_agent_proxy.cjs`
- Create: `tests/test_agent_user_credentials.py`
- Create: `src/ai/credential_envelope.py`
- Modify: `src/config.py`
- Modify: `src/models/schemas.py`
- Modify: `src/ai/gateway.py`
- Modify: `src/routes/ai.py`
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`

**Interfaces:**
- Consumes: `createAgentEnvelope(...)` and user model resolution.
- Produces: `decrypt_agent_envelope(envelope, expected_user_id, now=None) -> EphemeralCredential`.
- Produces: `AsyncModelGateway(model, credential=EphemeralCredential)` without touching `RUNTIME_CONFIG` or environment provider keys.

- [ ] **Step 1: Change the Node proxy test to require an encrypted envelope**

Assert the outgoing Agent body contains `credential_envelope`, contains no `api_key`, and does not contain the test plaintext anywhere in serialized headers or body. Assert the model and external user ID are protected inside the envelope rather than trusted as free-form routing metadata.

- [ ] **Step 2: Write failing Python envelope tests**

Cover valid decrypt, expired envelope, TTL above 60 seconds, wrong user, wrong key, tag tampering, unknown provider, mismatched model/provider, and replay nonce detection within the process window.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `python -m pytest tests/test_agent_user_credentials.py -q`
Run: `node --test tests/test_unicloud_agent_proxy.cjs`
Expected: both fail for missing envelope support.

- [ ] **Step 4: Implement Python envelope validation**

Add `AGENT_CREDENTIAL_KEY` to `src/config.py`, decode exactly 32 bytes, decrypt AES-GCM with the same AAD and JSON field names as Node, validate a maximum 60-second TTL, and keep a bounded in-process nonce cache until envelope expiry. Raise public credential errors without echoing input.

- [ ] **Step 5: Add explicit ephemeral credential support to the gateway**

Refactor `AsyncModelGateway` so an injected credential chooses the catalog allowlisted endpoint and protocol. Keep the existing environment-key constructor only for local development paths; `/internal/agent/tutor` must always supply the decrypted user credential.

- [ ] **Step 6: Wire the internal route**

Extend `AgentServiceTutorRequest` with `credential_envelope`. In `service_tutor`, authenticate `X-StructMind-Service-Key`, decrypt the envelope against `external_user_id`, and construct the orchestrator with the explicit credential. Reject requests without an envelope even if a global AI key exists.

- [ ] **Step 7: Update uniCloud Tutor forwarding**

Resolve the logged-in user's selected model, create a 60-second envelope, and forward it with the existing Agent payload. Keep conversation persistence and `structmind.agent.v1` event handling unchanged.

- [ ] **Step 8: Run Agent tests**

Run: `python -m pytest tests/test_agent_user_credentials.py tests/test_agent_orchestrator.py tests/test_agent_transports.py -q`
Run: `node --test tests/test_unicloud_agent_proxy.cjs`
Expected: PASS.

---

### Task 6: Desktop Web “My AI Models” Configuration Page

**Files:**
- Create: `pages/ai-settings/ai-settings.vue`
- Modify: `pages.json`
- Modify: `pages/ai/ai.vue`
- Modify: `pages/profile/profile.vue`
- Modify: `utils/cloud.js`
- Modify: `tests/test_unicloud_frontend.cjs`

**Interfaces:**
- Consumes cloud actions `getAIConfig`, `saveAIConfig`, `selectAIModel`, `testAIConnection`, and `deleteAIConfig`.
- Produces a desktop-first settings route with no client-side secret persistence.

- [ ] **Step 1: Write failing static UI and behavior assertions**

Check that the new page is registered, uses password inputs, lists all five exact model IDs, calls only the five user-level actions, and contains no `localStorage`, `uni.setStorage`, Base URL input, global provider key names, or hardcoded secret values.

- [ ] **Step 2: Run the frontend test and verify RED**

Run: `node --test tests/test_unicloud_frontend.cjs`
Expected: FAIL because the page is not present.

- [ ] **Step 3: Build the settings page**

Use a centered desktop content width, provider sections, model cards, configured/masked state, password input with explicit visibility toggle, and separate Save, Test, Select, and Delete actions. Never assign a returned masked key to the password input value. Require a confirmation dialog before delete.

- [ ] **Step 4: Add navigation and status**

Add a profile entry and an AI-page model status button that navigate to `/pages/ai-settings/ai-settings`. On `onShow`, refresh configuration so returning from settings updates the current model immediately.

- [ ] **Step 5: Preserve structured errors in the cloud wrapper**

Keep `error.code` as the stable AI error code and `error.data` as safe metadata. The UI maps `AI_CONFIG_REQUIRED`, `AI_CREDENTIAL_INVALID`, quota, timeout, and provider availability to direct Chinese recovery guidance.

- [ ] **Step 6: Run frontend tests**

Run: `node --test tests/test_unicloud_frontend.cjs tests/test_unicloud_learning_ui.cjs`
Expected: PASS.

---

### Task 7: Wire AI Feature UX to the Selected Model

**Files:**
- Modify: `pages/ai/ai.vue`
- Modify: `pages/practice/practice.vue`
- Modify: `pages/profile/profile.vue`
- Modify: `uniCloud-aliyun/cloudfunctions/api/index.js`
- Create: `tests/test_unicloud_ai_ui.cjs`

**Interfaces:**
- Consumes the public user AI config payload and stable error codes.
- Produces consistent selected-model labeling and configuration recovery paths across Tutor, question help, generation, assignment grading, and discussion grading.

- [ ] **Step 1: Write failing feature-state tests**

Assert every AI trigger handles an unconfigured user by linking to “我的 AI 模型”, displays the server-selected model rather than a browser-only value, and never sends a Base URL or API Key with feature calls.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test tests/test_unicloud_ai_ui.cjs`
Expected: FAIL because current pages do not share user configuration state.

- [ ] **Step 3: Add selected-model state to AI Tutor**

Load `getAIConfig` in `onShow`, render the selected model in the header, disable Send when no configured default exists, and redirect the configuration CTA to the settings page. Preserve standard/multi-agent switching and conversation reset behavior.

- [ ] **Step 4: Wire practice question help and generation**

Use the server-resolved default model; do not send stale model state from storage. On `AI_CONFIG_REQUIRED` or `AI_PROVIDER_NOT_CONFIGURED`, retain the student's current answer and offer configuration without resetting the practice session.

- [ ] **Step 5: Wire assignment and discussion grading adapters**

Call the dedicated actions and display provider/model metadata beside feedback. Preserve user answers on failures and show retry only for timeout, rate limit, and provider-unavailable errors.

- [ ] **Step 6: Run UI tests**

Run: `node --test tests/test_unicloud_ai_ui.cjs tests/test_unicloud_frontend.cjs tests/test_unicloud_learning_ui.cjs`
Expected: PASS.

---

### Task 8: Deployment Configuration, Documentation, and Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: tests only if full-suite failures expose a real regression

**Interfaces:**
- Consumes all prior tasks.
- Produces deployment instructions and evidence that no secret or global user-routing path remains.

- [ ] **Step 1: Document environment requirements without values**

Document `SM_USER_AI_MASTER_KEY`, `SM_AGENT_CREDENTIAL_KEY`, `SM_AGENT_CORE_URL`, and `SM_AGENT_SERVICE_KEY`. Include commands that generate fresh random Base64 values locally, but use placeholders in committed files. State that the two encryption keys must be different.

- [ ] **Step 2: Document deployment order**

Specify: deploy database schema/index, configure uniCloud secrets, configure matching Agent transport key and service key, deploy FastAPI Agent core, deploy `structmind-ai`, deploy the compatibility `api` cloud function, then rebuild/upload the uni-app H5 bundle.

- [ ] **Step 3: Run all Node tests**

Run: `node --test tests/*.cjs`
Expected: all tests pass.

- [ ] **Step 4: Run all Python tests**

Run: `$env:PYTHONPATH='.'; python -m pytest tests -q`
Expected: all tests pass.

- [ ] **Step 5: Run syntax and whitespace checks**

Run: `node --check uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`
Run: `node --check uniCloud-aliyun/cloudfunctions/structmind-ai/lib/provider-catalog.js`
Run: `node --check uniCloud-aliyun/cloudfunctions/structmind-ai/lib/credential-crypto.js`
Run: `node --check uniCloud-aliyun/cloudfunctions/structmind-ai/lib/user-ai-config.js`
Run: `node --check uniCloud-aliyun/cloudfunctions/structmind-ai/lib/model-gateway.js`
Run: `git diff --check`
Expected: all commands succeed with no output from `git diff --check`.

- [ ] **Step 6: Run a repository secret scan**

Search tracked source and generated H5 assets for common key prefixes and the exact environment variable values available to the test process. The scan must exclude `.git`, runtime databases, caches, user attachments, and local `.env`; it must return no credential content in source or build artifacts.

- [ ] **Step 7: Perform local mock integration smoke tests**

With fake provider responses, verify login → save provider key → masked reload → connection test → select model → Tutor → question help → generation → assignment grade → discussion grade → delete credential. Assert each recorded provider request uses the authenticated user's model.

- [ ] **Step 8: Perform production smoke tests with newly rotated user-owned keys**

Use the deployed domain and a non-admin test account. Test one configured provider at a time, verify model labels and all five feature categories, then delete the test credential. Do not capture API Key fields in screenshots or console logs.

- [ ] **Step 9: Review only task-related changes**

Run: `git status --short` and `git diff -- <task file list>`; confirm unrelated pre-existing UI and generated-output changes were not altered. Do not stage or commit unless the user explicitly authorizes it.

---

## Self-Review Result

- Spec coverage: provider allowlist, encryption at rest, encrypted Agent transport, user isolation, five feature categories, UI, error mapping, migration, deployment, and secret scanning are each assigned to a task.
- Placeholder scan: every implementation and verification step contains concrete files, interfaces, commands, and expected results.
- Type consistency: `provider_id`, `model_id`, `credential_envelope`, `ModelCredential`, and the five action names are consistent across Node, Python, cloud routes, and UI tasks.
- Scope split: the work spans several layers but is one security boundary and one end-to-end user feature; splitting into independent plans would leave intermediate states that either expose credentials or route some AI features globally.
