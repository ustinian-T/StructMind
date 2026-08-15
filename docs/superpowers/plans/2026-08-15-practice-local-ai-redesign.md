# Practice Local-First and AI Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the practice page immediately usable from the bundled 323-question local bank, grade answers locally, synchronize records opportunistically, expose AI generation as a separate persistent mode, and repair the desktop/mobile layout.

**Architecture:** A new pure ES module owns question normalization, local grading, AI response normalization, and local selection. `pages/practice/practice.vue` imports those functions, initializes from the bundled JSON synchronously, and treats cloud session/record synchronization as optional background enhancement. The page uses two source modes, `local` and `ai`, while sharing the existing answer view.

**Tech Stack:** uni-app Vue single-file components, JavaScript ES modules, Node.js built-in test runner, uniCloud cloud functions, scoped CSS.

## Global Constraints

- The bundled `runtime/exports/exam_questions.json` is the source of truth for the 323 local objective questions.
- Local practice must remain usable without login, network access, or deployed cloud question data.
- Cloud calls may synchronize sessions and attempts but must never replace or hide the local question list.
- AI generation is a separate practice source and must accept `generated`, `final_questions`, and legacy `questions` response fields.
- Preserve the existing route, navigation labels, StructMind wordmark, and green brand direction.
- Do not include `.idea/workspace.xml` or pre-existing generated-file changes in task commits.

---

### Task 1: Pure local practice domain module

**Files:**
- Create: `utils/practice-core.mjs`
- Create: `tests-js/practice-core.test.mjs`

**Interfaces:**
- Consumes: raw objects from `runtime/exports/exam_questions.json` and generated objects from the AI cloud function.
- Produces: `normalizePracticeQuestion(raw, source)`, `normalizeQuestionList(items, source)`, `gradePracticeAnswer(question, answer)`, `extractGeneratedQuestions(data)`, and `pickRandomQuestions(items, count, randomFn)`.

- [ ] **Step 1: Write failing tests for local normalization and the 323-question fixture**

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { normalizeQuestionList } from '../utils/practice-core.mjs'

test('normalizes all bundled exam questions for local practice', () => {
  const raw = JSON.parse(fs.readFileSync(new URL('../runtime/exports/exam_questions.json', import.meta.url)))
  const questions = normalizeQuestionList(raw, 'local')
  assert.equal(questions.length, 323)
  assert.equal(questions[0].id, 'EXAM_0001')
  assert.equal(questions[0].qtype, '单选题')
  assert.equal(questions[0].options[0].text.length > 0, true)
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: FAIL with module-not-found for `utils/practice-core.mjs`.

- [ ] **Step 3: Implement normalization**

Implement `TYPE_LABELS`, stable `id/source_id`, option `text`, `stem`, `answer`, `analysis`, and `practice_source` fields. Filter entries without an ID or stem.

- [ ] **Step 4: Add failing grading tests**

Cover exact single choice, unordered multi-choice, whitespace-insensitive fill blank, and an incorrect answer that returns the standard answer.

- [ ] **Step 5: Run the grading tests and verify RED**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: FAIL because `gradePracticeAnswer` is not exported.

- [ ] **Step 6: Implement local grading**

Return `{ is_correct, score, max_score, correct_answer, analysis, sync_status: 'local' }`. Normalize multi-choice with uppercase alphanumeric characters sorted before comparison.

- [ ] **Step 7: Add failing AI response and random-selection tests**

Assert that `extractGeneratedQuestions` prefers `final_questions`, falls back to `generated`, then `questions`, and that deterministic `pickRandomQuestions` returns unique entries without mutating the source.

- [ ] **Step 8: Implement AI response normalization and random selection, then verify GREEN**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: all tests PASS.

- [ ] **Step 9: Commit the domain module**

```bash
git add utils/practice-core.mjs tests-js/practice-core.test.mjs
git commit -m "feat(practice): add local question domain helpers"
```

### Task 2: Local-first page state and answer flow

**Files:**
- Modify: `pages/practice/practice.vue`
- Test: `tests-js/practice-core.test.mjs`

**Interfaces:**
- Consumes: Task 1 helpers and the default export from `runtime/exports/exam_questions.json`.
- Produces: page state `practiceSource`, `localQuestions`, `aiQuestions`, `syncState`, `syncMessage`; methods `activateSource(source)`, `loadLocalQuestions()`, `syncCloudSession()`, and `syncAttemptInBackground(question, answer, localResult)`.

- [ ] **Step 1: Add a failing source-isolation test**

Verify that normalization labels local and AI questions with different `practice_source` values and preserves local count after extracting AI results.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="source" tests-js/practice-core.test.mjs`
Expected: FAIL until the requested source metadata is present.

- [ ] **Step 3: Replace cloud-first initialization**

Import the JSON and helpers, initialize `localQuestions` synchronously in `mounted`, set the visible questions from the active source, derive chapters from the local set, then call `syncCloudSession()` without awaiting it for rendering.

- [ ] **Step 4: Make local selection operations pure page operations**

Change `startRandom10` to select ten local questions without calling `createSession`. Keep filtering, paging, list/swipe switching, and answer navigation on the current source only.

- [ ] **Step 5: Make answer submission local-first**

Call `gradePracticeAnswer` before any network request, assign the result immediately, clear `submitting`, and start background synchronization only when token, cloud session, and cloud document mapping are available.

- [ ] **Step 6: Keep synchronization non-blocking**

Use `syncState` only for status copy. On cloud failure preserve the local result, set `syncState = 'offline'`, and expose a retry action. Do not set a page-level `loadError` that replaces questions.

- [ ] **Step 7: Verify domain tests remain GREEN**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: all tests PASS.

- [ ] **Step 8: Commit the local-first page flow**

```bash
git add pages/practice/practice.vue tests-js/practice-core.test.mjs
git commit -m "fix(practice): make bundled bank the primary practice source"
```

### Task 3: Persistent AI generation workspace

**Files:**
- Modify: `pages/practice/practice.vue`
- Test: `tests-js/practice-core.test.mjs`

**Interfaces:**
- Consumes: `extractGeneratedQuestions(data)` and `normalizeQuestionList(items, 'ai')`.
- Produces: a visible source switch, inline AI form, AI result summary, and a “开始 AI 练习” action.

- [ ] **Step 1: Add failing tests for all current AI payload shapes**

Use representative `{ generated: [...] }`, `{ final_questions: [...] }`, and `{ questions: [...] }` payloads, including options with `value` instead of `text`.

- [ ] **Step 2: Run AI-focused tests and verify RED**

Run: `node --test --test-name-pattern="AI" tests-js/practice-core.test.mjs`
Expected: at least one payload-shape assertion FAILS before compatibility logic is complete.

- [ ] **Step 3: Replace the modal-only entry with an inline source workspace**

Add two top-level buttons, “本地练习” and “AI 出题”. In AI mode render chapter, type, difficulty, count, submit status, errors, configuration guidance, and generated result count within the main content column.

- [ ] **Step 4: Correct the AI cloud response contract**

Pass the cloud result through `extractGeneratedQuestions`, normalize into `aiQuestions`, set `practiceSource = 'ai'`, and keep `localQuestions` unchanged. Treat `publish_denied` as informational, not an error.

- [ ] **Step 5: Let generated questions enter the shared answer view**

Set `questions` from `aiQuestions`, reset filters and indices, and provide “重新生成” plus “返回本地题库” actions. Local grading remains available even when generated questions were not imported.

- [ ] **Step 6: Verify AI tests GREEN**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: all tests PASS.

- [ ] **Step 7: Commit the AI workspace**

```bash
git add pages/practice/practice.vue tests-js/practice-core.test.mjs
git commit -m "fix(practice): expose and repair AI question generation"
```

### Task 4: Responsive visual and interaction repair

**Files:**
- Modify: `pages/practice/practice.vue`

**Interfaces:**
- Consumes: the source and sync states from Tasks 2 and 3.
- Produces: centered content shell, responsive question grid, compact status bar, non-obscuring action dock, mobile single-column layout, focus styles, and reduced-motion behavior.

- [ ] **Step 1: Capture the current desktop page for comparison**

Use the existing local H5 preview and record a 1440x900 screenshot showing the excessive whitespace and oversized error state.

- [ ] **Step 2: Implement the content hierarchy**

Wrap the page in a maximum-width shell. Place title, source switch, sync status, filters, result count, and list/swipe control in order. Keep error text compact and adjacent to sync status.

- [ ] **Step 3: Repair list and answer layouts**

Use a two-column question grid above 980px and one column below it. Remove the fixed `calc(100vh - 340px)` list height so the document scrolls naturally. Keep answer content at a readable width.

- [ ] **Step 4: Repair the action dock and mobile layout**

Constrain the dock to the content shell, reserve bottom space, keep two primary local actions, and remove the redundant modal AI button. Below 640px use a compact two-column dock and full-width AI form controls.

- [ ] **Step 5: Add interaction and accessibility states**

Add visible keyboard focus, selected/disabled contrast, 44px targets, and `@media (prefers-reduced-motion: reduce)` rules that disable card transforms and animated pulses.

- [ ] **Step 6: Validate desktop and mobile interactions**

At 1440x900 and 390x844 verify: 323 questions appear, filters update counts, a card enters answer mode, local submission reveals the result immediately, source switching preserves local questions, and AI form controls remain reachable.

- [ ] **Step 7: Commit the visual repair**

```bash
git add pages/practice/practice.vue
git commit -m "style(practice): repair responsive layout and interactions"
```

### Task 5: Full regression and handoff

**Files:**
- Modify only if a verification failure identifies a task-scoped defect.

**Interfaces:**
- Consumes: all prior task deliverables.
- Produces: verified local-first practice and AI generation behavior.

- [ ] **Step 1: Run JavaScript tests**

Run: `node --test tests-js/practice-core.test.mjs`
Expected: all tests PASS with no warnings.

- [ ] **Step 2: Run Python regression tests**

Run: `python -m pytest tests -q`
Expected: all existing tests PASS.

- [ ] **Step 3: Run syntax and diff checks**

Run: `node --check utils/practice-core.mjs`
Expected: exit code 0.

Run: `git diff --check -- pages/practice/practice.vue utils/practice-core.mjs tests-js/practice-core.test.mjs`
Expected: no output.

- [ ] **Step 4: Build when a uni-app CLI is available**

Use HBuilderX “发行 → 网站-PC Web或手机H5” for this project. Expected: `unpackage/dist/build/web` is generated with no compile errors. Do not stage generated output unless explicitly requested.

- [ ] **Step 5: Perform final browser smoke test**

Serve the fresh H5 build and repeat the desktop/mobile acceptance path from Task 4. Inspect the browser console; expected: no uncaught exceptions or missing local-bank asset errors.

- [ ] **Step 6: Review task-only Git status**

Run: `git status --short`
Expected: existing unrelated `.idea/workspace.xml` and generated output changes remain untouched; task files are committed or explicitly listed for handoff.
