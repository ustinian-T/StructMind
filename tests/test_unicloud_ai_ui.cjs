'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');

test('AI settings page exposes five models and user-level actions only', () => {
  const pagePath = path.join(ROOT, 'pages/ai-settings/ai-settings.vue');
  assert.equal(fs.existsSync(pagePath), true);
  const source = fs.readFileSync(pagePath, 'utf8');
  for (const model of [
    'MiniMax-M3[1M]', 'deepseek-v4-flash', 'deepseek-v4-pro[1m]',
    'ark-code-latest', 'step-router-v1',
  ]) assert.equal(source.includes(model), true, model);
  for (const action of [
    'getAIConfig', 'saveAIConfig', 'selectAIModel', 'testAIConnection', 'deleteAIConfig',
  ]) assert.equal(source.includes(action), true, action);
  assert.equal(source.includes('type="password"'), true);
  assert.equal(/localStorage|uni\.setStorage|ANTHROPIC_AUTH_TOKEN|SM_AI_API_KEY/.test(source), false);
  assert.equal(/Base URL|base_url/.test(source), false);
});

test('AI settings route and entry points are registered', () => {
  const pages = fs.readFileSync(path.join(ROOT, 'pages.json'), 'utf8');
  const ai = fs.readFileSync(path.join(ROOT, 'pages/ai/ai.vue'), 'utf8');
  const profile = fs.readFileSync(path.join(ROOT, 'pages/profile/profile.vue'), 'utf8');
  assert.equal(pages.includes('pages/ai-settings/ai-settings'), true);
  assert.equal(ai.includes('/pages/ai-settings/ai-settings'), true);
  assert.equal(profile.includes('/pages/ai-settings/ai-settings'), true);
  assert.equal(ai.includes('getAIConfig'), true);
});
