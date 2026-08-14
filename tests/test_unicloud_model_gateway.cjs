'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const { callModel } = require(path.resolve(
  __dirname, '../uniCloud-aliyun/cloudfunctions/structmind-ai/lib/model-gateway.js',
));
const { getProvider, getModel } = require(path.resolve(
  __dirname, '../uniCloud-aliyun/cloudfunctions/structmind-ai/lib/provider-catalog.js',
));

function credential(modelId, apiKey = 'provider-secret') {
  const model = getModel(modelId);
  const provider = getProvider(model.provider_id);
  return {
    provider_id: provider.id, model_id: model.id, api_key: apiKey,
    protocol: provider.protocol, base_url: provider.base_url,
    auth_style: provider.auth_style, timeout_ms: provider.timeout_ms,
  };
}

function fakeClient(data, status = 200) {
  const requests = [];
  return {
    requests,
    async request(url, options) {
      requests.push({ url, options });
      return { status, data };
    },
  };
}

test('Anthropic request uses allowlisted MiniMax URL and extracts text', async () => {
  const httpclient = fakeClient({
    content: [{ type: 'thinking', thinking: 'hidden' }, { type: 'text', text: '你好' }],
    usage: { input_tokens: 2, output_tokens: 1 }, stop_reason: 'end_turn',
  });
  const result = await callModel({
    httpclient, credential: credential('MiniMax-M3[1M]'),
    messages: [{ role: 'system', content: 'system' }, { role: 'user', content: 'hi' }],
    maxTokens: 32,
  });
  assert.equal(httpclient.requests[0].url, 'https://api.minimaxi.com/anthropic/v1/messages');
  assert.equal(httpclient.requests[0].options.data.model, 'MiniMax-M3[1M]');
  assert.equal(httpclient.requests[0].options.data.system, 'system');
  assert.equal(result.content, '你好');
  assert.deepEqual(result.usage, { input_tokens: 2, output_tokens: 1 });
});

test('OpenAI request uses StepFun plan endpoint', async () => {
  const httpclient = fakeClient({
    choices: [{ message: { content: 'ok' }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 4, completion_tokens: 2 },
  });
  const result = await callModel({
    httpclient, credential: credential('step-router-v1'),
    messages: [{ role: 'user', content: 'hi' }], maxTokens: 16,
  });
  assert.equal(httpclient.requests[0].url, 'https://api.stepfun.com/step_plan/v1/chat/completions');
  assert.equal(httpclient.requests[0].options.data.model, 'step-router-v1');
  assert.equal(result.content, 'ok');
});

test('provider errors are normalized without leaking key or response body', async () => {
  const httpclient = fakeClient({ error: { message: 'provider-secret was rejected' } }, 401);
  await assert.rejects(
    callModel({
      httpclient, credential: credential('deepseek-v4-flash'),
      messages: [{ role: 'user', content: 'hi' }],
    }),
    error => error.code === 'AI_CREDENTIAL_INVALID'
      && !error.message.includes('provider-secret')
      && !error.message.includes('rejected'),
  );
});

test('rate limits use stable public code', async () => {
  const httpclient = fakeClient({ error: 'limit' }, 429);
  await assert.rejects(
    callModel({ httpclient, credential: credential('ark-code-latest'), messages: [] }),
    error => error.code === 'AI_QUOTA_EXCEEDED',
  );
});
