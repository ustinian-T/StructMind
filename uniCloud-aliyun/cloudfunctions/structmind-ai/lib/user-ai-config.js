'use strict';

const { listProviders, getProvider, getModel, providerForModel, aiError } = require('./provider-catalog');
const { encryptUserKey, decryptUserKey } = require('./credential-crypto');

function createUserAIConfigService({ collection, masterKey, now = () => Date.now() }) {
  if (!collection) throw new TypeError('collection is required');

  async function find(userId) {
    const result = await collection.where({ user_id: userId }).get();
    return result.data?.[0] || null;
  }

  async function save(document) {
    const existing = await find(document.user_id);
    if (existing) {
      const { _id: _ignoredId, ...updates } = document;
      await collection.doc(existing._id).update(updates);
      return { ...existing, ...updates };
    }
    const { _id: _ignoredId, ...insert } = document;
    const result = await collection.add(insert);
    return { _id: result.id, ...insert };
  }

  async function getPublicConfig(userId) {
    const record = await find(userId);
    const credentials = record?.credentials || {};
    const providers = listProviders().map(provider => {
      const stored = credentials[provider.id];
      return {
        id: provider.id,
        label: provider.label,
        models: provider.models.map(model => model.id),
        model_options: provider.models,
        configured: Boolean(stored),
        ai_configured: Boolean(stored),
        key_preview: stored ? `•••• ${stored.key_last4 || ''}` : '',
        updated_at: stored?.updated_at || null,
        last_test: record?.last_tests?.[provider.id] || null,
      };
    });
    const defaultModel = record?.default_model || '';
    return {
      providers,
      models: providers.flatMap(provider => provider.models),
      default_model: defaultModel,
      default_provider: defaultModel ? providerForModel(defaultModel).id : '',
      ai_configured: Boolean(defaultModel),
    };
  }

  async function saveCredential(userId, providerId, apiKey, modelId) {
    const provider = getProvider(providerId);
    if (modelId) {
      const model = getModel(modelId);
      if (model.provider_id !== provider.id) throw aiError('AI_MODEL_NOT_ALLOWED', '模型与服务商不匹配。');
    }
    const record = await find(userId);
    const timestamp = now();
    const credential = {
      ...encryptUserKey(apiKey, { userId, providerId: provider.id, masterKey, keyVersion: 1 }),
      updated_at: timestamp,
    };
    await save({
      user_id: userId,
      default_model: modelId || record?.default_model || provider.default_model,
      credentials: { ...(record?.credentials || {}), [provider.id]: credential },
      last_tests: record?.last_tests || {},
      created_at: record?.created_at || timestamp,
      updated_at: timestamp,
    });
    return getPublicConfig(userId);
  }

  async function selectModel(userId, modelId) {
    const model = getModel(modelId);
    const record = await find(userId);
    if (!record?.credentials?.[model.provider_id]) {
      throw aiError('AI_PROVIDER_NOT_CONFIGURED', '请先配置该模型所属平台的 API Key。');
    }
    await save({ ...record, default_model: model.id, updated_at: now() });
    return getPublicConfig(userId);
  }

  async function deleteCredential(userId, providerId) {
    const provider = getProvider(providerId);
    const record = await find(userId);
    if (!record) return getPublicConfig(userId);
    const credentials = { ...(record.credentials || {}) };
    delete credentials[provider.id];
    const defaultModel = record.default_model && getModel(record.default_model).provider_id === provider.id
      ? '' : record.default_model;
    await save({ ...record, credentials, default_model: defaultModel, updated_at: now() });
    return getPublicConfig(userId);
  }

  async function recordConnectionTest(userId, providerId, result) {
    const provider = getProvider(providerId);
    const record = await find(userId);
    if (!record) throw aiError('AI_CONFIG_REQUIRED', '请先保存 API Key。');
    const safeResult = {
      ok: Boolean(result.ok), code: String(result.code || ''),
      tested_at: now(), model_id: String(result.model_id || ''),
    };
    await save({
      ...record,
      last_tests: { ...(record.last_tests || {}), [provider.id]: safeResult },
      updated_at: now(),
    });
    return safeResult;
  }

  async function resolveUserModel(userId, requestedModel) {
    const record = await find(userId);
    const modelId = requestedModel || record?.default_model;
    if (!modelId) throw aiError('AI_CONFIG_REQUIRED', '请先在“我的 AI 模型”中完成配置。');
    const model = getModel(modelId);
    const provider = getProvider(model.provider_id);
    const stored = record?.credentials?.[provider.id];
    if (!stored) throw aiError('AI_PROVIDER_NOT_CONFIGURED', '当前模型的平台 API Key 尚未配置。');
    return {
      provider_id: provider.id,
      model_id: model.id,
      api_key: decryptUserKey(stored, { userId, providerId: provider.id, masterKey }),
      protocol: provider.protocol,
      base_url: provider.base_url,
      auth_style: provider.auth_style,
      timeout_ms: provider.timeout_ms,
      supports_tools: provider.supports_tools,
    };
  }

  return {
    getPublicConfig, saveCredential, selectModel, deleteCredential,
    recordConnectionTest, resolveUserModel,
  };
}

module.exports = { createUserAIConfigService };
