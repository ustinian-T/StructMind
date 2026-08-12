export async function callCloud(name, action, params = {}) {
  const response = await uniCloud.callFunction({
    name,
    data: { action, params },
  })
  const result = response?.result || {}
  if (result.code !== 0) {
    const error = new Error(result.message || '云服务请求失败')
    error.code = result.code
    error.data = result.data
    throw error
  }
  return result.data || {}
}

export function getErrorMessage(error, fallback = '请求失败，请稍后重试') {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error) return error
  try {
    const parsed = JSON.parse(JSON.stringify(error || {}))
    return parsed.message || parsed.errMsg || parsed.error || fallback
  } catch (e) {
    return fallback
  }
}

const TYPE_LABELS = {
  single_choice: '单选题',
  multi_choice: '多选题',
  true_false: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
}

export function normalizeCloudQuestion(question = {}) {
  return {
    ...question,
    id: question.id || question._id,
    qtype: question.qtype || TYPE_LABELS[question.type] || question.type || '',
    stem: question.stem || question.content || '',
    options: (question.options || []).map(option => ({
      ...option,
      text: option.text ?? option.value ?? '',
    })),
  }
}

export function normalizeCloudProfile(profile = {}) {
  const typeAccuracy = {}
  for (const [type, stats] of Object.entries(profile.type_stats || {})) {
    const label = TYPE_LABELS[type] || type
    const accuracy = typeof stats === 'number' ? stats : (stats?.accuracy || 0)
    typeAccuracy[label] = accuracy > 1 ? accuracy / 100 : accuracy
  }
  const chapterAccuracy = {}
  for (const [chapter, stats] of Object.entries(profile.chapter_stats || {})) {
    const accuracy = typeof stats === 'number' ? stats : (stats?.accuracy || 0)
    chapterAccuracy[chapter] = accuracy > 1 ? accuracy / 100 : accuracy
  }
  return {
    ...profile,
    total_attempts: profile.total_attempts ?? profile.total_questions_attempted ?? 0,
    practice_streak: profile.practice_streak ?? profile.current_streak ?? 0,
    type_accuracy: profile.type_accuracy || typeAccuracy,
    chapter_accuracy: profile.chapter_accuracy || chapterAccuracy,
    weak_concepts: profile.weak_concepts || (profile.weak_chapters || []).map(item => item.chapter),
    strong_concepts: profile.strong_concepts || (profile.strong_chapters || []).map(item => item.chapter),
  }
}
