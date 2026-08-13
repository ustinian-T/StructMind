'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(ROOT, file), 'utf8');

test('mobile answer loop sends idempotency and timing evidence', () => {
  const source = read('pages/practice/practice.vue');
  assert.match(source, /attemptTokens/);
  assert.match(source, /attempt_token:/);
  assert.match(source, /time_spent:/);
  assert.match(source, /mastery_changes/);
  assert.match(source, /error_reason/);
  assert.match(source, /next_review_at/);
  assert.match(source, /next_recommendation/);
  assert.match(source, /为什么推荐下一题/);
  assert.match(source, /startNextRecommendation/);
  assert.match(source, /question_ids: ids/);
  const cloud = read('uniCloud-aliyun/cloudfunctions/structmind-practice/index.js');
  assert.match(cloud, /question_ids = \[\]/);
  assert.match(cloud, /conditions\._id = db\.command\.in\(question_ids\)/);
});

test('mobile learning archive exposes plan reviews and editable notes', () => {
  const source = read('pages/profile/profile.vue');
  for (const token of ['getPlan', 'savePlan', 'getReviews', 'reviewFeedback', 'listNotes', 'createNote', 'updateNote']) {
    assert.match(source, new RegExp(token));
  }
  assert.match(source, /examDate/);
  assert.match(source, /dailyMinutes/);
  assert.match(source, /too_hard/);
  assert.match(source, /just_right/);
  assert.match(source, /too_easy/);
  assert.match(source, /is_archived/);
});

test('mobile tutor refreshes and renders cited rule summary', () => {
  const source = read('pages/ai/ai.vue');
  assert.match(source, /summarizeConversation/);
  assert.match(source, /conversationSummary/);
  assert.match(source, /message_id/);
  assert.match(source, /规则摘要/);
});
