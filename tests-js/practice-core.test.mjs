import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

import {
  extractGeneratedQuestions,
  getPracticeErrorCode,
  gradePracticeAnswer,
  normalizeQuestionList,
  pickRandomQuestions,
  selectPracticeQuestions,
  toQuestionTypeValue,
} from '../utils/practice-core.mjs'

test('normalizes all bundled exam questions for local practice', () => {
  const raw = JSON.parse(
    fs.readFileSync(new URL('../static/data/exam_questions.json', import.meta.url), 'utf8'),
  )

  const questions = normalizeQuestionList(raw, 'local')

  assert.equal(questions.length, 323)
  assert.equal(questions[0].id, 'EXAM_0001')
  assert.equal(questions[0].source_id, 'EXAM_0001')
  assert.equal(questions[0].qtype, '单选题')
  assert.equal(questions[0].practice_source, 'local')
  assert.equal(questions[0].options[0].text.length > 0, true)
})

test('grades single choice and returns the local standard answer', () => {
  const result = gradePracticeAnswer({ type: 'single_choice', answer: 'A', analysis: '解析' }, 'a')

  assert.equal(result.is_correct, true)
  assert.equal(result.correct_answer, 'A')
  assert.equal(result.analysis, '解析')
  assert.equal(result.sync_status, 'local')
})

test('grades multi choice without depending on answer order or separators', () => {
  const result = gradePracticeAnswer({ type: 'multi_choice', answer: 'A,C,D' }, ['d', 'A', 'c'])

  assert.equal(result.is_correct, true)
})

test('grades fill blank while ignoring whitespace', () => {
  const result = gradePracticeAnswer({ type: 'fill_blank', answer: '数据 抽象' }, ' 数据抽象 ')

  assert.equal(result.is_correct, true)
})

test('reports an incorrect local answer immediately', () => {
  const result = gradePracticeAnswer({ type: 'true_false', answer: 'B' }, 'A')

  assert.equal(result.is_correct, false)
  assert.equal(result.score, 0)
  assert.equal(result.correct_answer, 'B')
})

test('extracts AI questions from current and legacy response fields', () => {
  const finalItems = [{ content: 'final' }]
  const generatedItems = [{ content: 'generated' }]
  const legacyItems = [{ content: 'legacy' }]

  assert.equal(extractGeneratedQuestions({ final_questions: finalItems, generated: generatedItems }), finalItems)
  assert.equal(extractGeneratedQuestions({ generated: generatedItems }), generatedItems)
  assert.equal(extractGeneratedQuestions({ questions: legacyItems }), legacyItems)
  assert.deepEqual(extractGeneratedQuestions({}), [])
})

test('normalizes AI option values without changing the local source label', () => {
  const aiQuestions = normalizeQuestionList([{
    content: 'AI 题目',
    type: 'single_choice',
    options: [{ key: 'A', value: '选项内容' }],
    answer: 'A',
  }], 'ai')

  assert.equal(aiQuestions[0].practice_source, 'ai')
  assert.equal(aiQuestions[0].options[0].text, '选项内容')
})

test('picks unique random questions without mutating the source', () => {
  const source = [{ id: 1 }, { id: 2 }, { id: 3 }]
  const original = structuredClone(source)

  const selected = pickRandomQuestions(source, 2, () => 0)

  assert.deepEqual(selected.map((item) => item.id), [2, 3])
  assert.deepEqual(source, original)
})

test('keeps local and AI practice sources isolated', () => {
  const local = [{ id: 'LOCAL_1', practice_source: 'local' }]
  const ai = [{ id: 'AI_1', practice_source: 'ai' }]

  assert.equal(selectPracticeQuestions('local', local, ai), local)
  assert.equal(selectPracticeQuestions('ai', local, ai), ai)
  assert.equal(local.length, 1)
})

test('reads cloud error codes and maps visible question type labels', () => {
  assert.equal(getPracticeErrorCode({ code: 'AI_CONFIG_REQUIRED' }), 'AI_CONFIG_REQUIRED')
  assert.equal(getPracticeErrorCode(null), '')
  assert.equal(toQuestionTypeValue('多选题'), 'multi_choice')
  assert.equal(toQuestionTypeValue('未知题型'), '')
})
