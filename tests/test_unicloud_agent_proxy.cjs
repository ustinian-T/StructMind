'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const AI_MODULE = path.resolve(
  __dirname,
  '../uniCloud-aliyun/cloudfunctions/structmind-ai/index.js',
);

function createCloud() {
  const now = Date.now();
  const requests = [];
  const tables = {
    structmind_sessions: [{ token: 'token', user_id: 'user-1', expires_at: now + 60_000 }],
    structmind_users: [{ _id: 'user-1', status: 'approved', role: 'student' }],
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
        return {
          async get() {
            return { data: rows.filter(row => Object.entries(query).every(([key, value]) => row[key] === value)) };
          },
          async remove() { return { deleted: 0 }; },
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
        const id = `conv-${nextId++}`;
        rows.push({ _id: id, ...values });
        return { id };
      },
    };
  }
  const coreEvents = [
    { protocol: 'structmind.agent.v1', type: 'meta', run_id: 'run', sequence: 1, timestamp: '2026-08-12T00:00:00Z', mode: 'multi_agent', model: 'default' },
    { protocol: 'structmind.agent.v1', type: 'delta', run_id: 'run', sequence: 2, timestamp: '2026-08-12T00:00:01Z', content: '逐Token回复' },
    { protocol: 'structmind.agent.v1', type: 'done', run_id: 'run', sequence: 3, timestamp: '2026-08-12T00:00:02Z', finish_reason: 'stop' },
  ];
  const uniCloud = {
    database: () => ({ collection }),
    httpclient: {
      async request(url, options) {
        requests.push({ url, options });
        return {
          status: 200,
          data: { protocol: 'structmind.agent.v1', events: coreEvents, reply: '逐Token回复' },
        };
      },
    },
  };
  return { requests, tables, uniCloud, coreEvents };
}

function load(cloud) {
  global.uniCloud = cloud.uniCloud;
  process.env.SM_AGENT_CORE_URL = 'https://agent.example.com/';
  process.env.SM_AGENT_SERVICE_KEY = 'service-secret';
  process.env.SM_USER_AI_MASTER_KEY = Buffer.alloc(32, 7).toString('base64');
  process.env.SM_AGENT_CREDENTIAL_KEY = Buffer.alloc(32, 9).toString('base64');
  delete require.cache[AI_MODULE];
  return require(AI_MODULE).main;
}

test('tutor is a credentialed proxy preserving the FastAPI event protocol', async () => {
  const cloud = createCloud();
  const main = load(cloud);
  await main({
    action: 'saveAIConfig',
    params: {
      token: 'token', provider_id: 'deepseek', api_key: 'test-provider-key',
      model_id: 'deepseek-v4-flash',
    },
  }, {});
  const result = await main({
    action: 'tutor',
    params: { token: 'token', message: '解释栈', mode: 'multi-agent' },
  }, {});

  assert.equal(result.code, 0);
  assert.equal(cloud.requests.length, 1);
  assert.equal(cloud.requests[0].url, 'https://agent.example.com/api/internal/agent/tutor');
  assert.equal(cloud.requests[0].options.headers['X-StructMind-Service-Key'], 'service-secret');
  assert.equal(cloud.requests[0].options.headers.Authorization, undefined);
  assert.equal(cloud.requests[0].options.data.mode, 'multi_agent');
  assert.equal(typeof cloud.requests[0].options.data.credential_envelope.ciphertext, 'string');
  assert.equal(JSON.stringify(cloud.requests[0]).includes('test-provider-key'), false);
  assert.deepEqual(result.data.events, cloud.coreEvents);
  assert.equal(result.data.message, '逐Token回复');
  assert.equal(cloud.tables.structmind_ai_conversations[0].messages.length, 2);
  assert.deepEqual(
    cloud.tables.structmind_ai_conversations[0].messages.map(item => item.role),
    ['user', 'assistant'],
  );
});

test('uniCloud contains no duplicate Tutor prompt or direct Tutor model call', () => {
  const source = fs.readFileSync(AI_MODULE, 'utf8');
  assert.equal(source.includes('你是一位专业的数学辅导老师，使用苏格拉底式教学法指导学生'), false);
  const tutorBlock = source.slice(source.indexOf("case 'tutor'"), source.indexOf("case 'gradeDiscussion'"));
  assert.equal(tutorBlock.includes('callAI('), false);
  assert.equal(tutorBlock.includes('systemPrompt'), false);
});
