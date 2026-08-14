'use strict';

const crypto = require('node:crypto');
const { aiError } = require('./provider-catalog');

function decodeKey(value, variableName) {
  let key;
  try { key = Buffer.from(String(value || ''), 'base64'); }
  catch (_error) { key = Buffer.alloc(0); }
  if (key.length !== 32) {
    throw aiError('AI_CONFIG_REQUIRED', `${variableName} 必须是 Base64 编码的 32 字节密钥。`);
  }
  return key;
}

function userAAD(userId, providerId, keyVersion) {
  return Buffer.from(`${userId}:${providerId}:${keyVersion}`, 'utf8');
}

function encryptUserKey(apiKey, { userId, providerId, masterKey, keyVersion = 1 }) {
  const plaintext = String(apiKey || '').trim();
  if (!plaintext) throw aiError('AI_CREDENTIAL_INVALID', 'API Key 不能为空。');
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', decodeKey(masterKey, 'SM_USER_AI_MASTER_KEY'), iv);
  cipher.setAAD(userAAD(userId, providerId, keyVersion));
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return {
    ciphertext: ciphertext.toString('base64'),
    iv: iv.toString('base64'),
    auth_tag: cipher.getAuthTag().toString('base64'),
    key_version: keyVersion,
    key_last4: plaintext.slice(-4),
  };
}

function decryptUserKey(record, { userId, providerId, masterKey }) {
  try {
    const version = Number(record.key_version || 1);
    const decipher = crypto.createDecipheriv(
      'aes-256-gcm', decodeKey(masterKey, 'SM_USER_AI_MASTER_KEY'), Buffer.from(record.iv, 'base64'),
    );
    decipher.setAAD(userAAD(userId, providerId, version));
    decipher.setAuthTag(Buffer.from(record.auth_tag, 'base64'));
    return Buffer.concat([
      decipher.update(Buffer.from(record.ciphertext, 'base64')),
      decipher.final(),
    ]).toString('utf8');
  } catch (_error) {
    throw aiError('AI_CREDENTIAL_INVALID', '已保存的 AI 凭据无法解密，请重新配置。');
  }
}

function createAgentEnvelope(payload, transportKey) {
  const ttl = Number(payload.expires_at) - Number(payload.issued_at);
  if (!Number.isFinite(ttl) || ttl <= 0 || ttl > 60000) {
    throw aiError('AI_CREDENTIAL_INVALID', 'Agent 凭据有效期必须在 60 秒以内。');
  }
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(
    'aes-256-gcm', decodeKey(transportKey, 'SM_AGENT_CREDENTIAL_KEY'), iv,
  );
  cipher.setAAD(Buffer.from('structmind-agent-envelope:v1', 'utf8'));
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(payload), 'utf8'), cipher.final(),
  ]);
  return {
    version: 1,
    ciphertext: ciphertext.toString('base64'),
    iv: iv.toString('base64'),
    auth_tag: cipher.getAuthTag().toString('base64'),
  };
}

module.exports = { decodeKey, encryptUserKey, decryptUserKey, createAgentEnvelope };
