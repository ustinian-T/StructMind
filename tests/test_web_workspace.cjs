'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'web/index.html'), 'utf8');
const app = fs.readFileSync(path.join(ROOT, 'web/app.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'web/styles.css'), 'utf8');

test('web entry exposes accessible product metadata and skip navigation', () => {
  assert.match(html, /name="description"/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /href="#main-content"/);
  assert.match(html, /正在整理学习台/);
  assert.match(html, /STRUCTMIND_API_BASE/);
});

test('web shell is a learning workspace with semantic main and mobile navigation', () => {
  assert.match(app, /学习台/);
  assert.match(app, /id="main-content"/);
  assert.match(app, /class="bottom-nav"/);
  assert.match(app, /aria-current=/);
  assert.match(app, /系统状态/);
});

test('practice keeps the official bank visible and question centered', () => {
  assert.match(app, /source-official/);
  assert.match(app, /正式题库/);
  assert.match(app, /question-workspace/);
  assert.match(app, /question-stage/);
  assert.match(app, /question-context/);
});

test('AI tutor uses learning intents and a continuous conversation layout', () => {
  assert.match(app, /tutor-workspace/);
  assert.match(app, /tutor-thread/);
  assert.match(app, /tutor-message/);
  assert.match(app, /tutor-intent/);
  assert.match(app, /解释概念/);
  assert.match(app, /检查思路/);
  assert.match(app, /逐步提示/);
  assert.match(app, /生成变式题/);
});

test('answer provenance distinguishes official, Word and AI reference content', () => {
  assert.match(app, /source-word/);
  assert.match(app, /Word 作业答案/);
  assert.match(app, /source-ai/);
  assert.match(app, /AI 参考/);
});

test('design system covers viewport stability, focus and reduced motion', () => {
  assert.match(css, /100dvh/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /--z-modal/);
  assert.match(css, /\.bottom-nav/);
});

test('web theme uses a warm light-green learning palette without template styling', () => {
  assert.match(html, /name="theme-color" content="#f3f7f0"/);
  assert.match(css, /--bg:\s*#f3f7f0/);
  assert.match(css, /--surface-subtle:\s*#edf5e9/);
  assert.match(css, /--primary:\s*#477a50/);
  assert.match(css, /--ink:\s*#183229/);
  assert.doesNotMatch(css, /ChatGPT-inspired|"Inter"/i);
});

test('every web workspace shares polished navigation, forms, feedback and responsive states', () => {
  for (const selector of [
    '.learning-home', '.practice-builder', '.question-workspace',
    '.tutor-workspace', '.review-workspace', '.archive-workspace',
    '.discussion-workspace', '.table-wrap', '.modal', '.empty', '.result'
  ]) {
    assert.match(css, new RegExp(selector.replace('.', '\\\.')));
  }
  assert.match(css, /@media \(max-width:\s*47\.99rem\)/);
  assert.match(css, /@media \(hover:\s*hover\)/);
});

test('dialogs and startup errors remain accessible and recoverable', () => {
  assert.match(app, /role="dialog" aria-modal="true"/);
  assert.match(app, /aria-label="关闭登录窗口"/);
  assert.match(app, /id="retryBoot"/);
  assert.match(css, /\.boot-error/);
});

test('guest dashboard does not present global attempts as personal history', () => {
  assert.match(app, /const attempts = isLoggedIn\(\)/);
});

test('practice sessions send an optional numeric count accepted by the API schema', () => {
  assert.doesNotMatch(app, /count:'all'/);
  assert.doesNotMatch(app, /count:cnt\|\|'all'/);
  assert.match(app, /count:cnt\?Number\(cnt\):null/);
});

test('practice builder starts with the same ten-question session promised by the dashboard', () => {
  assert.match(app, /id="pCount"[^>]*value="10"/);
  assert.match(app, /10 题/);
});
