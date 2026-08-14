'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const AI_MODULE = path.resolve(__dirname, '../uniCloud-aliyun/cloudfunctions/structmind-ai/index.js');
const MASTER_KEY = Buffer.alloc(32, 7).toString('base64');

function createCloud() {
  const now = Date.now();
  const requests = [];
  const tables = {
    structmind_sessions: [
      { token: 'token-a', user_id: 'user-a', expires_at: now + 60000 },
      { token: 'token-b', user_id: 'user-b', expires_at: now + 60000 },
    ],
    structmind_users: [
      { _id: 'user-a', role: 'student', status: 'approved' },
      { _id: 'user-b', role: 'student', status: 'approved' },
    ],
    structmind_user_ai_configs: [], structmind_questions: [], structmind_assignments: [],
    structmind_discussions: [], structmind_ai_conversations: [], structmind_conv_summaries: [],
  };
  let serial = 1;
  function collection(name) {
    const rows = tables[name] || (tables[name] = []);
    return {
      where(query) {
        const matches = () => rows.filter(row => Object.entries(query).every(([key, value]) => row[key] === value));
        const chain = {
          async get() { return { data: matches() }; },
          async remove() { return { deleted: 0 }; },
          async count() { return { total: matches().length }; },
          limit() { return chain; }, orderBy() { return chain; }, skip() { return chain; }, field() { return chain; },
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
        const id = `${name}-${serial++}`;
        rows.push({ _id: id, ...values });
        return { id };
      },
    };
  }
  const uniCloud = {
    database: () => ({ collection }),
    httpclient: {
      async request(url, options) {
        requests.push({ url, options });
        const generated = JSON.stringify([{
          content: '测试题目内容足够长', options: [{ key: 'A', value: 'A' }],
          answer: 'A', explanation: '解释', difficulty: 1, tags: ['测试'],
        }]);
        if (url.includes('/chat/completions')) {
          return { status: 200, data: { choices: [{ message: { content: generated } }], usage: {} } };
        }
        return { status: 200, data: { content: [{ type: 'text', text: generated }], usage: {} } };
      },
    },
  };
  return { tables, requests, uniCloud };
}

function load(cloud) {
  global.uniCloud = cloud.uniCloud;
  process.env.SM_USER_AI_MASTER_KEY = MASTER_KEY;
  delete require.cache[AI_MODULE];
  return require(AI_MODULE).main;
}

test('two users route generation through their own configured providers', async () => {
  const cloud = createCloud();
  const main = load(cloud);
  await main({ action: 'saveAIConfig', params: {
    token: 'token-a', provider_id: 'deepseek', api_key: 'key-a', model_id: 'deepseek-v4-flash',
  } });
  await main({ action: 'saveAIConfig', params: {
    token: 'token-b', provider_id: 'stepfun', api_key: 'key-b', model_id: 'step-router-v1',
  } });
  await main({ action: 'generateQuestion', params: { token: 'token-a', chapter: '栈', count: 1 } });
  await main({ action: 'generateQuestion', params: { token: 'token-b', chapter: '树', count: 1 } });

  assert.equal(cloud.requests[0].url, 'https://api.deepseek.com/anthropic/v1/messages');
  assert.equal(cloud.requests[0].options.data.model, 'deepseek-v4-flash');
  assert.equal(cloud.requests[1].url, 'https://api.stepfun.com/step_plan/v1/chat/completions');
  assert.equal(cloud.requests[1].options.data.model, 'step-router-v1');
  assert.equal(JSON.stringify(cloud.tables.structmind_user_ai_configs).includes('key-a'), false);
  assert.equal(JSON.stringify(cloud.tables.structmind_user_ai_configs).includes('key-b'), false);
});

test('user cannot route to an unconfigured provider model', async () => {
  const cloud = createCloud();
  const main = load(cloud);
  await main({ action: 'saveAIConfig', params: {
    token: 'token-a', provider_id: 'deepseek', api_key: 'key-a', model_id: 'deepseek-v4-flash',
  } });
  const result = await main({ action: 'generateQuestion', params: {
    token: 'token-a', chapter: '栈', count: 1, model: 'step-router-v1',
  } });
  assert.equal(result.code, 'AI_PROVIDER_NOT_CONFIGURED');
  assert.equal(cloud.requests.length, 0);
});
