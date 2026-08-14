'use strict';

function aiError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

const PROVIDERS = Object.freeze([
  Object.freeze({
    id: 'minimax', label: 'MiniMax', protocol: 'anthropic',
    base_url: 'https://api.minimaxi.com/anthropic', auth_style: 'bearer',
    default_model: 'MiniMax-M3[1M]', timeout_ms: 120000, supports_tools: true,
    models: Object.freeze([{ id: 'MiniMax-M3[1M]', label: 'MiniMax M3 · 1M' }]),
  }),
  Object.freeze({
    id: 'deepseek', label: 'DeepSeek', protocol: 'anthropic',
    base_url: 'https://api.deepseek.com/anthropic', auth_style: 'x-api-key',
    default_model: 'deepseek-v4-flash', timeout_ms: 120000, supports_tools: true,
    models: Object.freeze([
      { id: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
      { id: 'deepseek-v4-pro[1m]', label: 'DeepSeek V4 Pro · 1M' },
    ]),
  }),
  Object.freeze({
    id: 'volcengine', label: '火山方舟', protocol: 'anthropic',
    base_url: 'https://ark.cn-beijing.volces.com/api/plan', auth_style: 'bearer',
    default_model: 'ark-code-latest', timeout_ms: 120000, supports_tools: true,
    models: Object.freeze([{ id: 'ark-code-latest', label: 'Ark Code Latest' }]),
  }),
  Object.freeze({
    id: 'stepfun', label: '阶跃星辰', protocol: 'openai',
    base_url: 'https://api.stepfun.com/step_plan/v1', auth_style: 'bearer',
    default_model: 'step-router-v1', timeout_ms: 120000, supports_tools: true,
    models: Object.freeze([{ id: 'step-router-v1', label: 'Step Router V1' }]),
  }),
]);

const PROVIDER_MAP = new Map(PROVIDERS.map(provider => [provider.id, provider]));
const MODEL_MAP = new Map();
for (const provider of PROVIDERS) {
  for (const model of provider.models) MODEL_MAP.set(model.id, { ...model, provider_id: provider.id });
}

function listProviders() {
  return PROVIDERS.map(provider => ({
    ...provider,
    models: provider.models.map(model => ({ ...model })),
  }));
}

function getProvider(providerId) {
  const provider = PROVIDER_MAP.get(String(providerId || '').trim());
  if (!provider) throw aiError('AI_PROVIDER_NOT_CONFIGURED', '不支持该 AI 服务商。');
  return provider;
}

function getModel(modelId) {
  const model = MODEL_MAP.get(String(modelId || '').trim());
  if (!model) throw aiError('AI_MODEL_NOT_ALLOWED', '该模型不在允许列表中。');
  return { ...model };
}

function providerForModel(modelId) {
  return getProvider(getModel(modelId).provider_id);
}

module.exports = { aiError, listProviders, getProvider, getModel, providerForModel };
