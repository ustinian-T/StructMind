'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '../uniCloud-aliyun/cloudfunctions/structmind-ai/lib');
const catalog = require(path.join(ROOT, 'provider-catalog.js'));
const {
  encryptUserKey,
  decryptUserKey,
  createAgentEnvelope,
} = require(path.join(ROOT, 'credential-crypto.js'));
const { createUserAIConfigService } = require(path.join(ROOT, 'user-ai-config.js'));

function memoryCollection() {
  const rows = [];
  let serial = 1;
  return {
    rows,
    where(query) {
      return {
        async get() {
          return { data: rows.filter(row => Object.entries(query).every(([key, value]) => row[key] === value)) };
        },
      };
    },
    doc(id) {
      return {
        async update(values) {
          const row = rows.find(item => item._id === id);
          if (row) Object.assign(row, values);
          return { updated: row ? 1 : 0 };
        },
      };
    },
    async add(values) {
      const id = `config-${serial++}`;
      rows.push({ _id: id, ...values });
      return { id };
    },
  };
}

const MASTER_KEY = Buffer.alloc(32, 7).toString('base64');
const TRANSPORT_KEY = Buffer.alloc(32, 9).toString('base64');

test('catalog exposes exactly four providers and five fixed models', () => {
  const providers = catalog.listProviders();
  assert.equal(providers.length, 4);
  assert.deepEqual(providers.flatMap(item => item.models.map(model => model.id)), [
    'MiniMax-M3[1M]',
    'deepseek-v4-flash',
    'deepseek-v4-pro[1m]',
    'ark-code-latest',
    'step-router-v1',
  ]);
  assert.throws(() => catalog.getModel('custom-model'), error => error.code === 'AI_MODEL_NOT_ALLOWED');
});

test('encrypted user key is bound to user and provider', () => {
  const encrypted = encryptUserKey('unit-test-secret', {
    userId: 'user-a', providerId: 'deepseek', masterKey: MASTER_KEY, keyVersion: 1,
  });
  assert.equal(JSON.stringify(encrypted).includes('unit-test-secret'), false);
  assert.equal(decryptUserKey(encrypted, {
    userId: 'user-a', providerId: 'deepseek', masterKey: MASTER_KEY,
  }), 'unit-test-secret');
  assert.throws(() => decryptUserKey(encrypted, {
    userId: 'user-b', providerId: 'deepseek', masterKey: MASTER_KEY,
  }), error => error.code === 'AI_CREDENTIAL_INVALID');
});

test('agent envelope rejects TTL over sixty seconds', () => {
  assert.throws(() => createAgentEnvelope({
    provider_id: 'deepseek', model_id: 'deepseek-v4-flash', api_key: 'secret',
    external_user_id: 'user-a', issued_at: 1000, expires_at: 61001, nonce: 'nonce',
  }, TRANSPORT_KEY), /60/);
});

test('user configuration is isolated, masked, and persists selection', async () => {
  const collection = memoryCollection();
  const service = createUserAIConfigService({ collection, masterKey: MASTER_KEY, now: () => 1234 });
  await service.saveCredential('user-a', 'deepseek', 'unit-test-secret', 'deepseek-v4-pro[1m]');
  await service.saveCredential('user-b', 'minimax', 'another-secret', 'MiniMax-M3[1M]');

  const publicA = await service.getPublicConfig('user-a');
  assert.equal(publicA.default_model, 'deepseek-v4-pro[1m]');
  assert.equal(publicA.providers.find(item => item.id === 'deepseek').configured, true);
  assert.equal(JSON.stringify(publicA).includes('unit-test-secret'), false);
  assert.equal((await service.getPublicConfig('user-b')).providers.find(item => item.id === 'deepseek').configured, false);

  const resolved = await service.resolveUserModel('user-a');
  assert.equal(resolved.api_key, 'unit-test-secret');
  assert.equal(resolved.provider_id, 'deepseek');
  assert.equal(resolved.model_id, 'deepseek-v4-pro[1m]');

  await service.deleteCredential('user-a', 'deepseek');
  const cleared = await service.getPublicConfig('user-a');
  assert.equal(cleared.default_model, '');
  assert.equal(cleared.providers.find(item => item.id === 'deepseek').configured, false);
});

test('selecting an unconfigured provider is rejected', async () => {
  const service = createUserAIConfigService({ collection: memoryCollection(), masterKey: MASTER_KEY });
  await assert.rejects(
    service.selectModel('user-a', 'step-router-v1'),
    error => error.code === 'AI_PROVIDER_NOT_CONFIGURED',
  );
});
