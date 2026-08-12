'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const PRACTICE = path.resolve(__dirname, '../uniCloud-aliyun/cloudfunctions/structmind-practice/index.js');
const LEARNING = path.resolve(__dirname, '../uniCloud-aliyun/cloudfunctions/structmind-learning/index.js');

function createCloud() {
  const now = Date.now();
  const tables = {
    structmind_users: [
      { _id: 'u1', status: 'approved' }, { _id: 'u2', status: 'approved' },
    ],
    structmind_sessions: [
      { _id: 's1', token: 'token-u1', user_id: 'u1', expires_at: now + 60000 },
      { _id: 's2', token: 'token-u2', user_id: 'u2', expires_at: now + 60000 },
    ],
    structmind_questions: [
      { _id: 'q1', type: 'single_choice', chapter: '栈和队列', content: '栈的特征是什么？', answer: 'B', explanation: '后进先出' },
      { _id: 'q2', type: 'single_choice', chapter: '栈和队列', content: '队列的特征是什么？', answer: 'A' },
    ],
    structmind_practice_sessions: [
      { _id: 'practice-1', user_id: 'u1', total: 2, completed: 0, correct: 0, wrong: 0, status: 'in_progress' },
    ],
    structmind_ai_conversations: [
      { _id: 'conversation-1', user_id: 'u1', messages: [
        { role: 'user', content: '我认为递归使用栈，但调用帧是什么？' },
        { role: 'assistant', content: '你已经完全掌握栈。' },
      ] },
    ],
  };
  let nextId = 1;
  const match = (row, query) => Object.entries(query).every(([key, value]) => row[key] === value);
  function collection(name) {
    const rows = tables[name] || (tables[name] = []);
    const queryApi = values => ({
      async get() { return { data: values() }; },
      async update(fields) { const found = values(); found.forEach(row => Object.assign(row, fields)); return { updated: found.length }; },
      limit(count) { return queryApi(() => values().slice(0, count)); },
      orderBy(key, direction) { return queryApi(() => [...values()].sort((a, b) => direction === 'desc' ? b[key] - a[key] : a[key] - b[key])); },
    });
    return {
      where(query) { return queryApi(() => rows.filter(row => match(row, query))); },
      doc(id) {
        return {
          async get() { return { data: rows.filter(row => row._id === id) }; },
          async update(fields) { const row = rows.find(item => item._id === id); if (row) Object.assign(row, fields); return { updated: row ? 1 : 0 }; },
        };
      },
      limit(count) { return queryApi(() => rows.slice(0, count)); },
      async add(fields) { const id = `${name}-${nextId++}`; rows.push({ _id: id, ...structuredClone(fields) }); return { id }; },
    };
  }
  return { tables, uniCloud: { database: () => ({ collection }) } };
}

function load(modulePath, cloud) {
  global.uniCloud = cloud.uniCloud;
  delete require.cache[modulePath];
  return require(modulePath).main;
}

test('uniCloud answer requires and replays attempt_token with complete loop', async () => {
  const cloud = createCloud();
  const main = load(PRACTICE, cloud);
  const base = { token: 'token-u1', session_id: 'practice-1', question_id: 'q1', user_answer: 'A', time_spent: 12 };
  const missing = await main({ action: 'submitAnswer', params: base }, {});
  assert.equal(missing.code, 400);
  assert.match(missing.message, /attempt_token/);

  const first = await main({ action: 'submitAnswer', params: { ...base, attempt_token: 'cloud-attempt-1' } }, {});
  const second = await main({ action: 'submitAnswer', params: { ...base, attempt_token: 'cloud-attempt-1' } }, {});
  assert.equal(first.code, 0);
  assert.equal(first.data.learning_event_id, second.data.learning_event_id);
  assert.ok(first.data.mastery_changes[0].delta < 0);
  assert.equal(first.data.error_reason.source, 'rule');
  assert.ok(first.data.review_updates[0].next_review_at);
  assert.ok(first.data.next_recommendation.explanation);
  assert.equal(first.data.enhancement_status, 'rule_only');
  assert.equal(cloud.tables.structmind_practice_records.length, 1);
  assert.equal(cloud.tables.structmind_learning_events.length, 1);
});

test('learning cloud function enforces ownership and creates cited rule summary', async () => {
  const cloud = createCloud();
  const practice = load(PRACTICE, cloud);
  const answer = await practice({ action: 'submitAnswer', params: {
    token: 'token-u1', session_id: 'practice-1', question_id: 'q1', user_answer: 'A',
    attempt_token: 'cloud-owner-1', time_spent: 8,
  } }, {});
  const learning = load(LEARNING, cloud);
  const own = await learning({ action: 'getEvent', params: {
    token: 'token-u1', event_id: answer.data.learning_event_id,
  } });
  const other = await learning({ action: 'getEvent', params: {
    token: 'token-u2', event_id: answer.data.learning_event_id,
  } });
  assert.equal(own.code, 0);
  assert.equal(other.code, 404);

  const summary = await learning({ action: 'summarizeConversation', params: {
    token: 'token-u1', conversation_id: 'conversation-1',
  } });
  assert.equal(summary.code, 0);
  const facts = summary.data.summary.summary_final.student_understanding;
  assert.ok(facts[0].message_id);
  assert.equal(facts.some(item => item.text.includes('完全掌握')), false);
});
