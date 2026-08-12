'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const AI_MODULE = path.resolve(
  __dirname,
  '../uniCloud-aliyun/cloudfunctions/structmind-ai/index.js',
);

function createCloud(role) {
  const now = Date.now();
  const tables = {
    structmind_sessions: [{
      _id: 'session-1', token: 'valid-token', user_id: 'user-1',
      created_at: now, expires_at: now + 60000,
    }],
    structmind_users: [{
      _id: 'user-1', account: role, role, status: 'approved',
    }],
    structmind_questions: [],
    structmind_assignments: [],
    structmind_discussions: [],
    structmind_ai_conversations: [],
  };
  let nextId = 1;

  function collection(name) {
    const rows = tables[name] || (tables[name] = []);
    return {
      where(query) {
        const matches = () => rows.filter(row =>
          Object.entries(query).every(([key, value]) => row[key] === value),
        );
        const chain = {
          async get() { return { data: matches() }; },
          limit() { return chain; },
          orderBy() { return chain; },
          skip() { return chain; },
          field() { return chain; },
          async count() { return { total: matches().length }; },
          async remove() { return { deleted: 0 }; },
        };
        return chain;
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
        rows.push({ _id: id, ...values });
        return { id };
      },
    };
  }

  const uniCloud = {
    database: () => ({ collection }),
    httpclient: {
      async request() {
        return {
          status: 200,
          data: {
            choices: [{
              message: {
                content: JSON.stringify([{
                  content: '栈 先进 后出 的正确描述是哪一项？',
                  options: [
                    { key: 'A', value: '先进先出' },
                    { key: 'B', value: '后进先出' },
                  ],
                  answer: 'B', explanation: '栈遵循后进先出。',
                  difficulty: 1, tags: ['栈'],
                }]),
              },
            }],
            usage: { total_tokens: 50 },
            model: 'test-model',
          },
        };
      },
    },
  };

  return { tables, uniCloud };
}

function loadAI(cloud) {
  global.uniCloud = cloud.uniCloud;
  process.env.SM_AI_API_KEY = 'test-key';
  delete require.cache[AI_MODULE];
  return require(AI_MODULE).main;
}

async function generate(main) {
  return main({
    action: 'generateQuestion',
    params: {
      token: 'valid-token', chapter: '栈和队列',
      type: 'single_choice', count: 1, auto_import: true,
    },
  }, {});
}

test('approved student cannot auto-publish AI questions to official collection', async () => {
  const cloud = createCloud('student');
  const result = await generate(loadAI(cloud));

  assert.equal(result.code, 0);
  assert.equal(cloud.tables.structmind_questions.length, 0);
  assert.deepEqual(result.data.imported, []);
  assert.equal(result.data.publish_denied, true);
});
test('administrator may explicitly publish generated AI questions', async () => {
  const cloud = createCloud('admin');
  const result = await generate(loadAI(cloud));

  assert.equal(result.code, 0);
  assert.equal(cloud.tables.structmind_questions.length, 1);
  assert.equal(result.data.imported.length, 1);
  assert.equal(result.data.publish_denied, false);
});
