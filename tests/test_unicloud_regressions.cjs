'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');

test('AI tutor conversation id is mutable when creating a new conversation', () => {
  const source = fs.readFileSync(path.join(
    ROOT, 'uniCloud-aliyun/cloudfunctions/structmind-ai/index.js',
  ), 'utf8');
  const tutorBlock = source.slice(source.indexOf("case 'tutor'"), source.indexOf("case 'gradeDiscussion'"));
  assert.equal(/const\s*\{\s*conversation_id/.test(tutorBlock), false);
  assert.match(tutorBlock, /let conversation_id\s*=\s*params\.conversation_id/);
});

test('practice completion accuracy uses the session total', () => {
  const source = fs.readFileSync(path.join(
    ROOT, 'uniCloud-aliyun/cloudfunctions/structmind-practice/index.js',
  ), 'utf8');
  assert.equal(source.includes('updateData.total > 0'), false);
  assert.match(source, /session\.total > 0/);
});
