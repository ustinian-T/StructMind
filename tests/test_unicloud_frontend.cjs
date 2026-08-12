'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const PAGE_FILES = [
  'pages/login/login.vue',
  'pages/register/register.vue',
  'pages/admin/admin.vue',
  'pages/index/index.vue',
  'pages/dashboard/dashboard.vue',
  'pages/practice/practice.vue',
  'pages/ai/ai.vue',
  'pages/profile/profile.vue',
  'pages/wrong/wrong.vue',
];

test('uni-app pages use uniCloud instead of the legacy REST deployment', () => {
  for (const relativePath of PAGE_FILES) {
    const source = fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
    assert.equal(source.includes('datastytest.tshai.top'), false, relativePath);
    assert.equal(/\/api\/(?:auth|admin|profile|stats|questions|answer|wrong|recommend|ai)\b/.test(source), false, relativePath);
  }
});

test('shared cloud adapter validates cloud function result codes', () => {
  const source = fs.readFileSync(path.join(ROOT, 'utils/cloud.js'), 'utf8');
  assert.match(source, /uniCloud\.callFunction/);
  assert.match(source, /result\.code !== 0/);
  assert.match(source, /throw error/);
});

test('App.uvue declares globalData instead of replacing the readonly runtime object', () => {
  const source = fs.readFileSync(path.join(ROOT, 'App.uvue'), 'utf8');
  assert.match(source, /defineOptions\s*\(\s*\{[\s\S]*globalData\s*:/);
  assert.equal(/getApp\(\)\.globalData\s*=/.test(source), false);
  assert.equal(/<template>[\s\S]*<\/template>/.test(source), false);
});

test('uni-app x components only use declared events and supported card animation', () => {
  const chat = fs.readFileSync(path.join(ROOT, 'components/SmChat.vue'), 'utf8');
  const practice = fs.readFileSync(path.join(ROOT, 'pages/practice/practice.vue'), 'utf8');
  assert.match(chat, /emits:\s*\[[^\]]*['"]update:scrollTop['"]/);
  assert.equal(practice.includes('uni.createAnimation'), false);
});

test('page scripts remain valid JavaScript after cloud migration', () => {
  for (const relativePath of PAGE_FILES) {
    const source = fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
    const script = source.match(/<script>([\s\S]*?)<\/script>/)?.[1] || '';
    const executable = script
      .replace(/^import\s+.*$/gm, '')
      .replace(/export\s+default/, 'return');
    assert.doesNotThrow(() => new Function(executable), relativePath);
  }
});
