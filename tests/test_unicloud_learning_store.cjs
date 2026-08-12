'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const STORE = path.join(ROOT, 'uniCloud-aliyun/cloudfunctions/common/structmind-learning-store/index.js');
const COLLECTIONS = [
  'learning_events', 'question_concepts', 'concept_mastery', 'mastery_changes',
  'review_feedback', 'recommendation_snapshots', 'conversation_summaries', 'learning_notes',
];

function createDb() {
  const tables = {};
  let nextId = 1;
  const matches = (row, query) => Object.entries(query).every(([key, value]) => row[key] === value);
  return {
    tables,
    collection(name) {
      const rows = tables[name] || (tables[name] = []);
      return {
        where(query) {
          return {
            async get() { return { data: rows.filter(row => matches(row, query)) }; },
            async update(values) {
              const found = rows.filter(row => matches(row, query));
              found.forEach(row => Object.assign(row, values));
              return { updated: found.length };
            },
          };
        },
        doc(id) {
          return {
            async get() { return { data: rows.filter(row => row._id === id) }; },
            async update(values) {
              const row = rows.find(item => item._id === id);
              if (row) Object.assign(row, values);
              return { updated: row ? 1 : 0 };
            },
          };
        },
        async add(values) {
          const id = `${name}-${nextId++}`;
          rows.push({ _id: id, ...structuredClone(values) });
          return { id };
        },
      };
    },
  };
}

test('learning collection schemas are parseable owner-scoped audit contracts', () => {
  for (const suffix of COLLECTIONS) {
    const filename = path.join(ROOT, `uniCloud-aliyun/database/structmind_${suffix}.schema.json`);
    const schema = JSON.parse(fs.readFileSync(filename, 'utf8'));
    assert.match(schema.permission.read, /doc\.user_id === auth\.uid/);
    assert.ok(schema.required.includes('user_id'));
    assert.ok(schema.properties.created_at);
    assert.ok(schema.properties.updated_at || suffix === 'mastery_changes');
  }
  const plan = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'uniCloud-aliyun/database/structmind_learning_plans.schema.json'), 'utf8',
  ));
  for (const field of ['exam_date', 'daily_minutes', 'timezone', 'version', 'status', 'plan_data']) {
    assert.ok(plan.properties[field], field);
  }
});

test('committed token replays and partial pending event is not readable', async () => {
  const db = createDb();
  const { createLearningStore } = require(STORE);
  const store = createLearningStore(db);
  const input = {
    userId: 'u1', attemptToken: 'token-1',
    draft: { question_id: 'q1', evaluated_at: '2026-08-12T00:00:00Z', rule_version: 'learning-loop-v1' },
    outcome: {
      response: { is_correct: false, rule_version: 'learning-loop-v1' },
      mastery_changes: [{ concept: '栈', after_score: 0.35, review: { next_review_at: '2026-08-13T00:00:00Z' } }],
    },
  };
  const first = await store.commitLearningEvent(input);
  const second = await store.commitLearningEvent(input);
  assert.deepEqual(second, first);
  assert.equal(db.tables.structmind_learning_events.length, 1);

  db.tables.structmind_learning_events.push({
    _id: 'pending-1', user_id: 'u1', attempt_token: 'pending-token', status: 'pending',
  });
  await assert.rejects(() => store.getLearningEvent('u1', 'pending-1'), /不存在/);
  await assert.rejects(() => store.getLearningEvent('u2', first.learning_event_id), /不存在/);
});

test('pending event is recovered in place instead of duplicated', async () => {
  const db = createDb();
  const input = {
    userId: 'u1', attemptToken: 'recover-1',
    draft: { question_id: 'q1', evaluated_at: '2026-08-12T00:00:00Z', rule_version: 'learning-loop-v1' },
    outcome: { response: { is_correct: true }, mastery_changes: [] },
  };
  db.tables.structmind_learning_events = [{
    _id: 'event-existing', user_id: 'u1', attempt_token: 'recover-1', status: 'pending',
    draft: structuredClone(input.draft), outcome: structuredClone(input.outcome), created_at: 1, updated_at: 1,
  }];
  const { createLearningStore } = require(STORE);
  const store = createLearningStore(db);
  const response = await store.recoverPendingEvent('u1', 'recover-1');
  assert.equal(response.learning_event_id, 'event-existing');
  assert.equal(db.tables.structmind_learning_events.length, 1);
  assert.equal(db.tables.structmind_learning_events[0].status, 'committed');
});
