# StructMind Phase 2 Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, offline-capable, traceable learning loop across FastAPI/Web and uniCloud/uni-app so every authenticated answer records mastery changes and returns a persisted explanation for the next recommendation.

**Architecture:** A versioned deterministic learning-rules contract is implemented once in Python and once in JavaScript and locked by shared JSON golden vectors. Each runtime owns its storage and transaction/state-machine adapter, while answer submission calls one orchestrator that persists the event, mastery changes, review schedule, rule error reason, recommendation snapshot, and plan progress before returning. AI enhancement remains asynchronous and optional; Web and uni-app render the same semantic response fields.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLite, pytest; Node.js `node:test`, uniCloud database/cloud functions, uni-app Vue; Vanilla JavaScript Web UI, Playwright.

## Global Constraints

- Cover both browser Web/FastAPI/SQLite and uni-app/uniCloud.
- Core grading, mastery, review, error classification, recommendation, planning, rule summary, and notes must work without AI.
- A question has one primary concept and zero or more secondary concepts; weights sum to 1.0, defaulting to 0.7/0.3.
- Every authenticated official-bank answer returns a unique `learning_event_id`, at least one persisted mastery change, and a persisted next-recommendation explanation when a next question exists.
- `attempt_token` is required for authenticated loop writes and is idempotent per user.
- AI enhancement never overwrites rule output or user-confirmed error reasons and never rolls back a core answer transaction.
- Keep official question-bank answers as the sole truth for objective grading.
- Preserve current API compatibility fields while adding the authoritative loop fields.
- Preserve unrelated dirty-worktree changes; stage and commit only task-related files.
- Store instants in UTC; pass `evaluated_at` explicitly into deterministic rules; round cross-runtime floats to four decimals.

---

### Task 1: Shared deterministic contract and golden vectors

**Files:**
- Create: `tests/fixtures/learning_loop_vectors.json`
- Create: `src/learning/__init__.py`
- Create: `src/learning/contracts.py`
- Create: `src/learning/rules.py`
- Create: `uniCloud-aliyun/cloudfunctions/common/structmind-learning-rules/index.js`
- Create: `tests/test_learning_rules.py`
- Create: `tests/test_learning_rules.cjs`

**Interfaces:**
- Consumes: question stem/chapter/type/options, normalized user/correct answers, current concept/review state, plan context, candidate questions, and an explicit UTC evaluation time.
- Produces: `resolve_concepts()`, `update_mastery()`, `schedule_review()`, `classify_error()`, `score_recommendations()`, `build_plan()`, and `summarize_conversation()` with `rule_version="learning-loop-v1"` in both runtimes.

- [ ] **Step 1: Write shared golden cases**

Add vectors for: primary-only correct answer; weighted primary/secondary incorrect answer; answer-format error; unclassified error; overdue review; equal-score deterministic tie; limited time budget; expired exam; and rule-only conversation summary. Expected floats use four decimals and times use UTC ISO 8601.

- [ ] **Step 2: Write failing Python contract tests**

```python
@pytest.mark.parametrize("case", load_vectors("mastery"))
def test_mastery_vectors(case):
    assert update_mastery(**case["input"]) == case["expected"]

def test_concept_fallback_always_returns_a_primary():
    concepts = resolve_concepts("无法命中词典", "第九章", [])
    assert concepts == [{"concept": "第九章", "role": "primary", "weight": 1.0,
                         "source": "chapter_fallback", "confidence": 0.4}]
```

- [ ] **Step 3: Run Python tests and verify RED**

Run: `python -m pytest tests/test_learning_rules.py -q`

Expected: FAIL because `src.learning.rules` does not exist.

- [ ] **Step 4: Implement the focused Python rules**

Use frozen dataclasses or typed dictionaries for concept, mastery, review, error reason, recommendation, plan, and summary results. Keep all functions pure; do not import database or FastAPI modules.

- [ ] **Step 5: Run Python tests and verify GREEN**

Run: `python -m pytest tests/test_learning_rules.py -q`

- [ ] **Step 6: Write failing Node parity tests**

```javascript
test('JavaScript mastery output matches shared vectors', () => {
  for (const item of vectors.mastery) {
    assert.deepEqual(rules.updateMastery(item.input), item.expected);
  }
});
```

- [ ] **Step 7: Run Node tests and verify RED**

Run: `node --test tests/test_learning_rules.cjs`

Expected: FAIL because the common rules module does not exist.

- [ ] **Step 8: Implement JavaScript parity and verify GREEN**

Implement the same constants, enum strings, rounding, UTC arithmetic, sorting, and fallback behavior without random numbers.

Run: `node --test tests/test_learning_rules.cjs`

- [ ] **Step 9: Commit the shared contract**

```bash
git add tests/fixtures/learning_loop_vectors.json tests/test_learning_rules.py tests/test_learning_rules.cjs src/learning uniCloud-aliyun/cloudfunctions/common/structmind-learning-rules/index.js
git commit -m "feat: define deterministic learning loop rules"
```

### Task 2: SQLite schema and atomic learning-event repository

**Files:**
- Modify: `src/db/database.py`
- Create: `src/learning/repository.py`
- Create: `tests/test_learning_repository.py`

**Interfaces:**
- Consumes: a `LearningEventDraft` and calculated rule results.
- Produces: `PracticeDatabase.commit_learning_event(draft, outcome) -> dict`, `get_learning_event(user_id, event_id)`, `get_due_reviews(user_id, evaluated_at)`, `save_review_feedback(...)`, and idempotent replay by `(user_id, attempt_token)`.

- [ ] **Step 1: Add failing migration and transaction tests**

Assert the new tables/indexes exist, migration can run twice, idempotent replay returns the original response, rollback leaves no event/mastery changes after an injected recommendation-write failure, and owner-scoped event retrieval rejects another user.

- [ ] **Step 2: Run repository tests and verify RED**

Run: `python -m pytest tests/test_learning_repository.py -q`

- [ ] **Step 3: Add idempotent schema migration**

Create `learning_events`, `question_concepts`, `mastery_changes`, `review_feedback`, `recommendation_snapshots`, `conversation_summaries`, and `learning_notes`. Extend `concept_mastery` through column-existence checks with `review_state`, `last_learning_event_id`, and `rule_version`. Add unique index `(user_id, attempt_token)` and owner/time indexes.

- [ ] **Step 4: Implement one-connection repository transaction**

Do not call existing methods that open nested SQLite connections. Accept one connection, insert the event, upsert mastery/review states, insert change rows and recommendation snapshot, update plan progress, then store a serialized response snapshot used for idempotent replay.

- [ ] **Step 5: Verify RED-to-GREEN and legacy compatibility**

Run: `python -m pytest tests/test_learning_repository.py tests/test_core.py -q`

- [ ] **Step 6: Commit SQLite persistence**

```bash
git add src/db/database.py src/learning/repository.py tests/test_learning_repository.py
git commit -m "feat: persist atomic learning events"
```

### Task 3: FastAPI answer-loop orchestration and trace endpoints

**Files:**
- Create: `src/learning/service.py`
- Modify: `src/models/schemas.py`
- Modify: `src/routes/practice.py`
- Modify: `src/routes/learning.py`
- Modify: `src/services/recommendation.py`
- Create: `tests/test_learning_api.py`

**Interfaces:**
- Consumes: authenticated `AnswerRequest` with `attempt_token`, optional `session_id`, `time_spent_seconds`, official question, profile/plan/recent evidence, and deterministic rules.
- Produces: `LearningLoopService.submit_answer(...)`; `GET /api/learning/events/{event_id}`; explainable `POST /api/recommend/questions`; `GET /api/learning/reviews`; `POST /api/learning/reviews/feedback`.

- [ ] **Step 1: Add failing endpoint tests**

Test authenticated submission returns `learning_event_id`, `mastery_changes`, `error_reason`, `review_updates`, `next_recommendation`, `recommendation_snapshot_id`, `plan_progress`, and `enhancement_status="rule_only"`. Test anonymous compatibility omits the user loop, duplicate token replays, event ownership is enforced, and every recommendation includes score breakdown and explanation.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `python -m pytest tests/test_learning_api.py -q`

- [ ] **Step 3: Extend request/response schemas**

Add `attempt_token: str | None`, `session_id: str | None`, and bounded `time_spent_seconds`. Add review feedback and event-query models. Authenticated official-bank submissions require a non-empty token; anonymous and assignment compatibility paths remain supported without mastery writes.

- [ ] **Step 4: Implement `LearningLoopService`**

Resolve concepts, read current states and recent evidence, calculate all rule outputs, select an official next question deterministically, build a student explanation, and pass the full draft to the atomic repository. Keep grading in `grade_answer()`.

- [ ] **Step 5: Replace randomized recommendation behavior**

Remove `random.uniform()` and `random.shuffle()` from personalized recommendations. Return one explanation per item plus stable `recommendation_snapshot_id` when the recommendation follows an answer event.

- [ ] **Step 6: Add trace and review routes**

Return owner-scoped immutable evidence and due-review queues. Feedback accepts only `too_easy`, `just_right`, or `too_hard` and records the resulting next interval.

- [ ] **Step 7: Verify focused and security tests**

Run: `python -m pytest tests/test_learning_api.py tests/test_security.py tests/test_core.py -q`

- [ ] **Step 8: Commit the FastAPI loop**

```bash
git add src/learning/service.py src/models/schemas.py src/routes/practice.py src/routes/learning.py src/services/recommendation.py tests/test_learning_api.py
git commit -m "feat: close the FastAPI answer loop"
```

### Task 4: Versioned exam plan, rule summaries, and learning notes

**Files:**
- Modify: `src/db/database.py`
- Modify: `src/models/schemas.py`
- Modify: `src/routes/learning.py`
- Modify: `src/routes/ai.py`
- Create: `tests/test_learning_plan_notes.py`

**Interfaces:**
- Consumes: exam date, daily minutes, IANA timezone, current mastery/reviews, conversation messages, and optional note edits.
- Produces: versioned current/history plan endpoints; rule summary endpoints; note CRUD/filter/archive; automatic answer and conversation notes.

- [ ] **Step 1: Add failing plan tests**

Assert `daily_minutes` accepts 10-480, exam date cannot be before the user's local today, plan tasks stay within the daily budget, no task is after the exam, changing settings supersedes rather than deletes the old version, and expired plans return `expired`.

- [ ] **Step 2: Add failing summary/note tests**

Assert rule summaries work with no AI client, include message/evidence references, never mark assistant claims as student mastery, auto-note refresh preserves `user_content`, filters are owner-scoped, and archive/restore works.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `python -m pytest tests/test_learning_plan_notes.py -q`

- [ ] **Step 4: Implement versioned plan persistence and routes**

Replace delete-and-insert planning with `version`, `active/superseded/expired`, `exam_date`, `daily_minutes`, `timezone`, and immutable plan snapshots. Update `generate_learning_plan_data()` to delegate to pure `build_plan()`.

- [ ] **Step 5: Implement rule summary and notes**

Generate a rule summary after a completed tutor turn and an automatic note after an incorrect answer. Store `auto_content` separately from `user_content`. AI enhancement, if later invoked, writes only the AI enhancement field and status.

- [ ] **Step 6: Verify focused tests and existing Agent transports**

Run: `python -m pytest tests/test_learning_plan_notes.py tests/test_agent_transports.py tests/test_core.py -q`

- [ ] **Step 7: Commit planning and notes**

```bash
git add src/db/database.py src/models/schemas.py src/routes/learning.py src/routes/ai.py tests/test_learning_plan_notes.py
git commit -m "feat: add exam plans summaries and notes"
```

### Task 5: uniCloud schemas and recoverable core persistence

**Files:**
- Create: `uniCloud-aliyun/database/structmind_learning_events.schema.json`
- Create: `uniCloud-aliyun/database/structmind_question_concepts.schema.json`
- Create: `uniCloud-aliyun/database/structmind_concept_mastery.schema.json`
- Create: `uniCloud-aliyun/database/structmind_mastery_changes.schema.json`
- Create: `uniCloud-aliyun/database/structmind_review_feedback.schema.json`
- Create: `uniCloud-aliyun/database/structmind_recommendation_snapshots.schema.json`
- Create: `uniCloud-aliyun/database/structmind_conversation_summaries.schema.json`
- Create: `uniCloud-aliyun/database/structmind_learning_notes.schema.json`
- Modify: `uniCloud-aliyun/database/structmind_learning_plans.schema.json`
- Create: `uniCloud-aliyun/cloudfunctions/common/structmind-learning-store/index.js`
- Create: `tests/test_unicloud_learning_store.cjs`

**Interfaces:**
- Consumes: authenticated user ID, idempotency token, and deterministic loop outcome.
- Produces: `commitLearningEvent()`, `recoverPendingEvent()`, `getLearningEvent()`, due-review and note/plan storage helpers. Only `committed` events participate in profile/recommendation reads.

- [ ] **Step 1: Add failing schema and fake-database tests**

Assert owner permissions, required audit fields, token uniqueness contract, `pending -> committed` transition, replay of a committed token, recovery of a pending token, and no partial event exposed by read helpers.

- [ ] **Step 2: Run Node tests and verify RED**

Run: `node --test tests/test_unicloud_learning_store.cjs`

- [ ] **Step 3: Add schemas and storage adapter**

Prefer `db.startTransaction()` when available. Provide the explicit state-machine fallback required by the spec: reserve idempotency token as `pending`, write child documents tagged with event ID, conditionally mark `committed`, and recover/complete the same event on retry. Never create a second event for the token.

- [ ] **Step 4: Verify GREEN and schema parsing**

Run: `node --test tests/test_unicloud_learning_store.cjs tests/test_unicloud_auth.cjs`

- [ ] **Step 5: Commit cloud persistence**

```bash
git add uniCloud-aliyun/database uniCloud-aliyun/cloudfunctions/common/structmind-learning-store/index.js tests/test_unicloud_learning_store.cjs
git commit -m "feat: add recoverable uniCloud learning storage"
```

### Task 6: uniCloud answer loop, reviews, plans, summaries, and notes

**Files:**
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-practice/index.js`
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-stats/index.js`
- Modify: `uniCloud-aliyun/cloudfunctions/structmind-ai/index.js`
- Create: `uniCloud-aliyun/cloudfunctions/structmind-learning/index.js`
- Create: `uniCloud-aliyun/cloudfunctions/structmind-learning/package.json`
- Modify: `uniCloud-aliyun/cloudfunctions/api/index.js`
- Create: `tests/test_unicloud_learning_loop.cjs`

**Interfaces:**
- Consumes: `submitAnswer` with `attempt_token`; common rules/store; existing question/session/stat collections.
- Produces: the same semantic answer fields as FastAPI plus `getEvent`, `recommend`, `getReviews`, `reviewFeedback`, `savePlan`, `getPlan`, `summarizeConversation`, and notes actions.

- [ ] **Step 1: Add failing cloud-function contract tests**

Use a fake uniCloud database to prove answer submission calls rules/store, requires and replays `attempt_token`, rejects another user's session/event/note, returns rule-only data when no AI settings exist, and excludes `pending` events from recommendations.

- [ ] **Step 2: Run Node tests and verify RED**

Run: `node --test tests/test_unicloud_learning_loop.cjs`

- [ ] **Step 3: Refactor `submitAnswer` around the common orchestrator**

Keep existing session/stat compatibility fields but move record, mastery, review, error, recommendation, and plan updates into the recoverable store. Eliminate random recommendation order for personalized/due modes.

- [ ] **Step 4: Add the learning cloud function**

Implement owner-scoped event/review/plan/summary/note actions. Rule summary must not call the external Agent core or direct AI. Optional enhancement is a separate action/status and may fail without affecting saved rule data.

- [ ] **Step 5: Extend tutor persistence with rule summaries**

After the existing FastAPI Agent response is stored, calculate and save the rule summary with message references. Do not make Tutor availability a prerequisite for reading or regenerating summaries from stored messages.

- [ ] **Step 6: Verify all cloud tests**

Run: `node --test tests/test_unicloud_learning_loop.cjs tests/test_unicloud_regressions.cjs tests/test_unicloud_ai_permissions.cjs tests/test_unicloud_auth.cjs`

- [ ] **Step 7: Commit cloud behavior**

```bash
git add uniCloud-aliyun/cloudfunctions/structmind-practice uniCloud-aliyun/cloudfunctions/structmind-stats uniCloud-aliyun/cloudfunctions/structmind-ai uniCloud-aliyun/cloudfunctions/structmind-learning uniCloud-aliyun/cloudfunctions/api/index.js tests/test_unicloud_learning_loop.cjs
git commit -m "feat: close the uniCloud answer loop"
```

### Task 7: Web learning-loop workspace

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_web_workspace.cjs`
- Create: `tests/test_web_learning_loop.cjs`

**Interfaces:**
- Consumes: FastAPI answer/recommend/review/plan/event/summary/note contracts.
- Produces: idempotent answer submission, inline mastery/error/review/recommendation evidence, exam-plan controls, review center, and learning archive.

- [ ] **Step 1: Add failing Web source/behavior contract tests**

Assert the client generates one stable token per unanswered question, reuses it on retry, renders `mastery_changes`, `error_reason`, `next_review_at`, `next_recommendation.explanation`, plan `exam_date`/`daily_minutes`, review feedback controls, summaries, notes, and rule-only status.

- [ ] **Step 2: Run Web tests and verify RED**

Run: `node --test tests/test_web_learning_loop.cjs tests/test_web_workspace.cjs`

- [ ] **Step 3: Extend Web state and answer submission**

Track `attemptTokens`, `learningPlan`, `dueReviews`, `learningEvents`, `conversationSummary`, and `notes`. `submitBankAnswer()` sends the session ID/time and reuses its token until the question is reset.

- [ ] **Step 4: Render the inline answer loop**

Show primary/secondary mastery deltas, final/rule error reason, review date, and a clear next-question reason with expandable evidence. Use `enhancement_status` to label rule-only output without presenting it as an error.

- [ ] **Step 5: Add plan, review, and archive views**

Use the existing navigation shell: enhance 学习台 with exam/time fields and real daily tasks; replace the basic wrong list with due/overdue/error groups and feedback; add summaries/notes to a 学习档案 section without removing existing functions.

- [ ] **Step 6: Verify Web tests**

Run: `node --test tests/test_web_learning_loop.cjs tests/test_web_workspace.cjs tests/test_unicloud_frontend.cjs`

- [ ] **Step 7: Commit Web UI**

```bash
git add static/app.js static/styles.css tests/test_web_workspace.cjs tests/test_web_learning_loop.cjs
git commit -m "feat: expose the learning loop on Web"
```

### Task 8: uni-app learning-loop experience

**Files:**
- Modify: `utils/cloud.js`
- Modify: `pages/practice/practice.vue`
- Modify: `pages/dashboard/dashboard.vue`
- Modify: `pages/wrong/wrong.vue`
- Modify: `pages/ai/ai.vue`
- Modify: `pages/profile/profile.vue`
- Modify: `pages.json`
- Create: `pages/archive/archive.vue`
- Create: `tests/test_unicloud_learning_ui.cjs`

**Interfaces:**
- Consumes: uniCloud answer/learning actions.
- Produces: stable retry token, inline loop result, real plan/due-review dashboard data, review feedback, and archive/notes/summary UI.

- [ ] **Step 1: Add failing uni-app source-contract tests**

Assert answer submission includes/reuses `attempt_token`; the result template renders mastery, error, review, and recommendation explanation; dashboard edits exam date/daily minutes; review sends three feedback enums; archive loads summaries and notes; no AI availability guard blocks rule data.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `node --test tests/test_unicloud_learning_ui.cjs`

- [ ] **Step 3: Add shared normalizers and stable tokens**

Extend `utils/cloud.js` with `normalizeLearningResult()` and a UUID-compatible token helper. Cache the current token in page state and clear it only when moving/resetting the question after a committed response.

- [ ] **Step 4: Upgrade practice, dashboard, and review pages**

Render the same semantic fields and labels as Web. Dashboard reads actual plan/review data. Review page groups by due/error reason and records difficulty feedback instead of only listing recent wrong questions.

- [ ] **Step 5: Add learning archive and tutor summary access**

Archive supports event trace, summary viewing, note edit, pin, filter, archive, and restore. Tutor page exposes the latest rule summary even if AI is currently unavailable.

- [ ] **Step 6: Verify uni-app source contracts**

Run: `node --test tests/test_unicloud_learning_ui.cjs tests/test_unicloud_frontend.cjs tests/test_unicloud_regressions.cjs`

The planning audit confirmed `C:\Program Files\HBuilderX\cli.exe` is absent, so no local HBuilder build may be claimed. Treat the Node source-contract suites above as the local gate and record H5 compilation/deployment as an explicit external verification item.

- [ ] **Step 7: Commit uni-app UI**

```bash
git add utils/cloud.js pages/practice/practice.vue pages/dashboard/dashboard.vue pages/wrong/wrong.vue pages/ai/ai.vue pages/profile/profile.vue pages/archive/archive.vue pages.json tests/test_unicloud_learning_ui.cjs
git commit -m "feat: expose the learning loop in uni-app"
```

### Task 9: Cross-runtime, regression, and real-browser acceptance

**Files:**
- Modify when required: task-scoped files above
- Update: `README.md`
- Artifacts: `output/playwright/learning-loop-*.png`

**Interfaces:**
- Consumes: completed dual-runtime implementation.
- Produces: fresh verification evidence for every hard acceptance criterion.

- [ ] **Step 1: Run deterministic parity tests together**

Run: `python -m pytest tests/test_learning_rules.py -q`

Run: `node --test tests/test_learning_rules.cjs`

Confirm both consume the same fixture and emit no mismatches.

- [ ] **Step 2: Run the complete Python suite**

Run: `python -m pytest tests -q`

Expected: zero failures.

- [ ] **Step 3: Run every Node suite**

Run each `tests/test_*.cjs` through `node --test` in one invocation.

Expected: zero failures.

- [ ] **Step 4: Run syntax and patch checks**

Run: `python -m compileall -q server.py src tests`

Run: `git diff --check`

- [ ] **Step 5: Execute an offline acceptance harness**

With AI keys unset, create an approved test user and submit at least two answers. Assert each event has mastery changes, an error reason when wrong, review scheduling, a persisted recommendation explanation, idempotent replay, updated plan progress, a rule conversation summary, and an automatic note.

- [ ] **Step 6: Verify Web in a real browser**

Start `python server.py`, then use Playwright at 1440x900 and 390x844. Complete login, plan settings, answer submission, mastery/reason expansion, next recommendation, review feedback, tutor summary, and note edit. Capture screenshots and check the console for uncaught errors.

- [ ] **Step 7: Audit all 12 hard acceptance criteria**

Map each criterion from `docs/superpowers/specs/2026-08-12-learning-loop-phase2-design.md` to a passing test, database query, API response, or browser artifact. Report any live uniCloud deployment item separately rather than claiming it was verified locally.

- [ ] **Step 8: Update documentation and commit final verification fixes**

Document the new endpoints, offline guarantee, rule version, migrations, and deployment schema/cloud-function list.

```bash
git add README.md
git commit -m "docs: document the phase 2 learning loop"
```
