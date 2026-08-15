const TYPE_LABELS = {
  single_choice: '单选题',
  multi_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
}

export function normalizePracticeQuestion(raw = {}, source = 'local', fallbackId = '') {
  const sourceId = raw.source_id || raw.question_id || raw.id || raw._id || fallbackId
  const type = raw.type || ''
  const stem = raw.stem || raw.content || ''

  return {
    ...raw,
    id: raw.id || raw._id || sourceId,
    source_id: sourceId,
    type,
    qtype: raw.qtype || TYPE_LABELS[type] || type,
    stem,
    options: (raw.options || []).map((option) => ({
      ...option,
      text: option.text ?? option.value ?? '',
    })),
    answer: raw.answer ?? '',
    analysis: raw.analysis || raw.explanation || '',
    practice_source: source,
  }
}

export function normalizeQuestionList(items, source = 'local') {
  if (!Array.isArray(items)) return []
  return items
    .map((item, index) => normalizePracticeQuestion(
      item,
      source,
      source === 'ai' ? `AI_${String(index + 1).padStart(4, '0')}` : '',
    ))
    .filter((item) => item.id && item.stem)
}

function normalizeChoiceAnswer(value) {
  const text = Array.isArray(value) ? value.join('') : String(value ?? '')
  return text.toUpperCase().replace(/[^A-Z0-9]/g, '').split('').sort().join('')
}

function normalizeTextAnswer(value) {
  return String(value ?? '').trim().replace(/\s+/g, '')
}

export function gradePracticeAnswer(question = {}, userAnswer = '') {
  const type = question.type || ''
  const correctAnswer = question.answer ?? ''
  const isMulti = type === 'multi_choice' || question.qtype === '多选题'
  const isText = type === 'fill_blank' || question.qtype === '填空题'
  let isCorrect

  if (isMulti) {
    isCorrect = normalizeChoiceAnswer(userAnswer) === normalizeChoiceAnswer(correctAnswer)
  } else if (isText) {
    isCorrect = normalizeTextAnswer(userAnswer) === normalizeTextAnswer(correctAnswer)
  } else {
    isCorrect = String(userAnswer ?? '').trim().toUpperCase()
      === String(correctAnswer).trim().toUpperCase()
  }

  return {
    is_correct: isCorrect,
    score: isCorrect ? 1 : 0,
    max_score: 1,
    correct_answer: correctAnswer,
    analysis: question.analysis || question.explanation || '',
    sync_status: 'local',
  }
}

export function extractGeneratedQuestions(data = {}) {
  if (Array.isArray(data.final_questions) && data.final_questions.length) return data.final_questions
  if (Array.isArray(data.generated) && data.generated.length) return data.generated
  if (Array.isArray(data.questions) && data.questions.length) return data.questions
  return []
}

export function pickRandomQuestions(items, count, randomFn = Math.random) {
  const pool = Array.isArray(items) ? [...items] : []
  for (let index = pool.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(randomFn() * (index + 1))
    ;[pool[index], pool[swapIndex]] = [pool[swapIndex], pool[index]]
  }
  return pool.slice(0, Math.max(0, Math.min(Number(count) || 0, pool.length)))
}
