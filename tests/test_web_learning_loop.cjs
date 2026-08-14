'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(ROOT, 'web/app.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'web/styles.css'), 'utf8');

test('web answer submissions use one stable idempotency token with timing context', () => {
  assert.match(app, /attemptTokens/);
  assert.match(app, /crypto\.randomUUID/);
  assert.match(app, /attempt_token/);
  assert.match(app, /session_id/);
  assert.match(app, /time_spent_seconds/);
});

test('web renders complete answer-loop evidence and next recommendation reason', () => {
  for (const field of ['mastery_changes', 'before_score', 'after_score', 'error_reason',
    'next_review_at', 'next_recommendation', 'score_breakdown', 'enhancement_status']) {
    assert.match(app, new RegExp(field));
  }
  assert.match(app, /为什么推荐下一题/);
  assert.match(app, /规则基础结果/);
  assert.match(app, /data-start-recommendation/);
});

test('web learning workspace includes exam plan, review feedback and archive controls', () => {
  assert.match(app, /exam_date/);
  assert.match(app, /daily_minutes/);
  assert.match(app, /learningPlan/);
  assert.match(app, /dueReviews/);
  assert.match(app, /too_easy/);
  assert.match(app, /just_right/);
  assert.match(app, /too_hard/);
  assert.match(app, /conversationSummary/);
  assert.match(app, /learning\/notes/);
  assert.match(app, /is_archived/);
});

test('learning-loop UI has responsive evidence layout and accessible controls', () => {
  assert.match(css, /\.learning-evidence/);
  assert.match(css, /\.mastery-change/);
  assert.match(css, /\.plan-settings/);
  assert.match(css, /\.review-queue/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(app, /[—–]/);
});
