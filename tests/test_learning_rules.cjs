'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const vectors = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'fixtures', 'learning_loop_vectors.json'),
  'utf8',
));
const rules = require('../uniCloud-aliyun/cloudfunctions/common/structmind-learning-rules');

test('JavaScript mastery output matches shared vectors', () => {
  for (const item of vectors.mastery) {
    assert.deepEqual(rules.updateMastery(item.input), item.expected, item.name);
  }
});

test('JavaScript review output matches shared vectors', () => {
  for (const item of vectors.reviews) {
    assert.deepEqual(rules.scheduleReview(item.input), item.expected, item.name);
  }
});

test('JavaScript error output matches shared vectors', () => {
  for (const item of vectors.errors) {
    assert.deepEqual(rules.classifyError(item.input), item.expected, item.name);
  }
});

test('JavaScript recommendation order is deterministic and explainable', () => {
  for (const item of vectors.recommendations) {
    const result = rules.scoreRecommendations(item.input);
    assert.deepEqual(result.map(entry => entry.question_id), item.expected_question_ids, item.name);
    assert.ok(result.every(entry => entry.score_breakdown && entry.explanation), item.name);
  }
});

test('JavaScript plan output matches shared vectors', () => {
  for (const item of vectors.plans) {
    assert.deepEqual(rules.buildPlan(item.input), item.expected, item.name);
  }
});

test('JavaScript rule summary matches shared vectors', () => {
  for (const item of vectors.summaries) {
    assert.deepEqual(rules.summarizeConversation(item.input), item.expected, item.name);
  }
});

test('JavaScript fallback always returns a primary concept', () => {
  assert.deepEqual(rules.resolveConcepts({
    stem: '无法命中词典', chapter: '第九章', curatedConcepts: [],
  }), [{
    concept: '第九章', role: 'primary', weight: 1,
    source: 'chapter_fallback', confidence: 0.4,
  }]);
});
