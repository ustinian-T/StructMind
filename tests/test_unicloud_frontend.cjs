'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const read = relativePath => fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
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

test('uniCloud build has one frontend source and never copies the FastAPI SPA as static assets', () => {
  for (const file of ['index.html', 'app.js', 'styles.css']) {
    assert.equal(fs.existsSync(path.join(ROOT, 'static', file)), false, `static/${file}`);
    assert.equal(fs.existsSync(path.join(ROOT, 'web', file)), true, `web/${file}`);
  }
  const server = read('server.py');
  assert.match(server, /WEB_DIR/);
  assert.match(server, /PUBLIC_DIR/);
});

test('App keeps shared light-green design tokens', () => {
  const app = read('App.uvue');
  assert.match(app, /--sm-bg:\s*#f3f7f0/);
  assert.match(app, /--sm-primary:\s*#477a50/);
});

test('desktop shell owns vertical scrolling and keeps the scrollbar usable', () => {
  const desktop = read('static/desktop.css');
  assert.match(desktop, /uni-page-wrapper\s*\{[\s\S]*overflow-y:\s*auto/);
  assert.match(desktop, /scrollbar-width:\s*thin/);
  assert.match(desktop, /::-webkit-scrollbar-thumb/);
  assert.match(desktop, /overscroll-behavior-y:\s*contain/);
});

test('home page provides restrained ambient particles, light effects and glass actions', () => {
  const home = read('pages/index/index.vue');
  const desktop = read('static/desktop.css');
  assert.match(home, /class="hero-particles"/);
  assert.match(home, /class="particle p1"/);
  assert.match(home, /class="hero-orbit/);
  assert.match(desktop, /@keyframes\s+smParticleFloat/);
  assert.match(desktop, /\.index-page \.hero-banner[\s\S]*radial-gradient/);
  assert.match(desktop, /\.index-page \.action-card[\s\S]*backdrop-filter:\s*blur/);
  assert.match(desktop, /\.prompt-btn[\s\S]*backdrop-filter:\s*blur/);
});

test('primary uni-app pages use source-specific desktop containers and avoid decorative emoji', () => {
  const forbidden = /[📝🤖🎯📖📊🔍🎉🔐✅❌📚📋]/u;
  for (const relativePath of PAGE_FILES) {
    const source = read(relativePath);
    assert.doesNotMatch(source, forbidden, relativePath);
  }
});

test('H5 template loads an unscoped desktop shell that can style uni-app runtime chrome', () => {
  const template = read('index.html');
  const desktopCssPath = path.join(ROOT, 'static', 'desktop.css');

  assert.match(template, /href="\/static\/desktop\.css\?v=[^"]+"/);
  assert.equal(fs.existsSync(desktopCssPath), true, 'static/desktop.css');

  const desktop = fs.readFileSync(desktopCssPath, 'utf8');
  assert.match(desktop, /@media\s*\(min-width:\s*900px\)/);
  assert.match(desktop, /\.uni-tabbar-bottom/);
  assert.match(desktop, /uni-page-wrapper/);
  assert.match(desktop, /grid-template-columns:\s*repeat\(4,/);
  assert.match(desktop, /\.ai-page\s+\.mode-switch-bar/);
  assert.doesNotMatch(desktop, /\[data-v-/);
});
