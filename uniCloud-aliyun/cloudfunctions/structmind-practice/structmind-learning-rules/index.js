// @ts-nocheck
'use strict';

const RULE_VERSION = 'learning-loop-v1';
const WEIGHTS = {
  due_base: 20, due_per_day: 5, due_cap: 40, mastery_gap: 30,
  error_match: 20, exam_urgent: 10, plan_match: 10, novelty: 5,
  repeat_each: 5, repeat_cap: 20,
};
const CONCEPT_KEYWORDS = [
  ['二叉树遍历', ['二叉树', '遍历']], ['图的遍历', ['图', '遍历']],
  ['递归', ['递归', '调用栈']], ['栈', ['栈', '后进先出']],
  ['队列', ['队列', '先进先出']], ['哈希', ['哈希', '散列']],
  ['排序', ['排序', '快排', '归并']],
];

function round4(value) { return Math.round((Number(value) + Number.EPSILON) * 10000) / 10000; }
function clamp(value, low = 0, high = 1) { return Math.min(high, Math.max(low, Number(value))); }
function isoAfterDays(value, days) {
  const date = new Date(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().replace('.000Z', 'Z');
}

function resolveConcepts({ stem, chapter, curatedConcepts = [] }) {
  const ordered = [];
  for (const raw of curatedConcepts) {
    const concept = String(raw || '').trim();
    if (concept && !ordered.some(item => item[0] === concept)) ordered.push([concept, 'curated', 1]);
  }
  if (!ordered.length) {
    for (const [concept, keywords] of CONCEPT_KEYWORDS) {
      if (keywords.some(keyword => String(stem || '').includes(keyword))) {
        ordered.push([concept, 'keyword_rule', 0.75]);
      }
    }
  }
  if (!ordered.length) {
    return [{ concept: String(chapter || '').trim() || '未分章', role: 'primary', weight: 1,
      source: 'chapter_fallback', confidence: 0.4 }];
  }
  const primaryWeight = ordered.length === 1 ? 1 : 0.7;
  const secondaryWeight = round4((1 - primaryWeight) / Math.max(1, ordered.length - 1));
  const result = ordered.map(([concept, source, confidence], index) => ({
    concept, role: index === 0 ? 'primary' : 'secondary',
    weight: index === 0 ? primaryWeight : secondaryWeight, source, confidence,
  }));
  const correction = round4(1 - result.reduce((sum, item) => sum + item.weight, 0));
  result[result.length - 1].weight = round4(result[result.length - 1].weight + correction);
  return result;
}

function updateMastery({ concept, role, weight, current, is_correct, consecutive_correct = 0 }) {
  const before = Number(current.mastery_score ?? 0.5);
  const alpha = is_correct && consecutive_correct >= 2 ? 0.33 : 0.3;
  const target = is_correct ? 1 : 0;
  const after = round4(clamp(before + alpha * Number(weight) * (target - before)));
  return {
    concept, role, weight: round4(weight), before_score: round4(before), after_score: after,
    delta: round4(after - before), alpha: round4(alpha),
    total_attempts: Number(current.total_attempts || 0) + 1,
    correct_attempts: Number(current.correct_attempts || 0) + (is_correct ? 1 : 0),
    rule_version: RULE_VERSION,
  };
}

function scheduleReview({ current, is_correct, weight, evaluated_at, feedback = null }) {
  if (feedback !== null && !['too_easy', 'just_right', 'too_hard'].includes(feedback)) {
    throw new Error('feedback must be too_easy, just_right, or too_hard');
  }
  const beforeStability = Number(current.stability ?? 1);
  const beforeDifficulty = Number(current.difficulty ?? 0.3);
  const boundedWeight = clamp(weight);
  let afterDifficulty;
  let targetStability;
  if (is_correct) {
    afterDifficulty = clamp(beforeDifficulty - 0.1 * boundedWeight);
    targetStability = beforeStability * (1 + 0.5 * (1 - afterDifficulty));
  } else {
    afterDifficulty = clamp(beforeDifficulty + 0.2 * boundedWeight);
    targetStability = Math.max(0.5, beforeStability * 0.5);
  }
  const afterStability = beforeStability + boundedWeight * (targetStability - beforeStability);
  const attempts = Number(current.total_attempts || 0);
  let interval;
  let state;
  if (attempts === 0) {
    interval = is_correct ? 3 : 1;
    state = is_correct ? 'learning' : 'relearning';
  } else if (!is_correct) {
    interval = 1;
    state = 'relearning';
  } else {
    interval = Math.max(1, Math.trunc(afterStability * (1 - afterDifficulty) * 7));
    state = 'review';
  }
  if (feedback === 'too_easy') interval = Math.max(1, Math.trunc(interval * 1.5));
  if (feedback === 'too_hard') interval = Math.max(1, Math.trunc(interval * 0.6));
  return {
    before_stability: round4(beforeStability), after_stability: round4(afterStability),
    before_difficulty: round4(beforeDifficulty), after_difficulty: round4(afterDifficulty),
    review_state: state, interval_days: interval,
    next_review_at: isoAfterDays(evaluated_at, interval), rule_version: RULE_VERSION,
  };
}

function compactAnswer(value) {
  return String(value ?? '').replace(/[\s,.，。;；:：()（）\[\]【】]+/g, '').toLocaleLowerCase();
}

function classifyError({ is_correct, qtype, user_answer, correct_answer, time_spent_seconds, mastery_score }) {
  let category; let subcategory; let confidence; let evidence;
  if (!is_correct && compactAnswer(user_answer) === compactAnswer(correct_answer)) {
    [category, subcategory, confidence, evidence] = ['answer_format', 'equivalent_after_compaction', 0.95, ['compact_answers_match']];
  } else if (!is_correct && time_spent_seconds !== null && time_spent_seconds !== undefined && Number(time_spent_seconds) <= 3) {
    [category, subcategory, confidence, evidence] = ['guessing', 'very_short_response_time', 0.8, ['time_spent_seconds<=3']];
  } else if (!is_correct && qtype === '多选题') {
    const userSet = new Set(String(user_answer).toUpperCase().replace(/[^A-H]/g, ''));
    const correctSet = new Set(String(correct_answer).toUpperCase().replace(/[^A-H]/g, ''));
    const subset = userSet.size > 0 && userSet.size < correctSet.size && [...userSet].every(value => correctSet.has(value));
    [category, subcategory, confidence, evidence] = subset
      ? ['reading_omission', 'missing_required_options', 0.75, ['selected_options_are_subset']]
      : ['unclassified', 'insufficient_evidence', 0.3, ['no_specific_rule_matched']];
  } else if (!is_correct && mastery_score !== null && mastery_score !== undefined && Number(mastery_score) < 0.5) {
    [category, subcategory, confidence, evidence] = ['concept_gap', 'low_prior_mastery', 0.65, ['mastery_score<0.5']];
  } else {
    [category, subcategory, confidence, evidence] = ['unclassified', 'insufficient_evidence', 0.3, ['no_specific_rule_matched']];
  }
  return { category, subcategory, confidence, evidence, source: 'rule', rule_version: RULE_VERSION };
}

function stableId(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? [0, numeric] : [1, String(value)];
}

function scoreRecommendations({ candidates, context, limit }) {
  const errors = new Set(context.recent_error_concepts || []);
  const plans = new Set(context.plan_concepts || []);
  const scored = candidates.map(candidate => {
    const concepts = new Set(candidate.concepts || []);
    const dueDays = Math.max(0, Number(candidate.due_days || 0));
    const mastery = clamp(candidate.mastery_score ?? 0.5);
    const exposures = Math.max(0, Number(candidate.recent_exposures || 0));
    const intersects = (left, right) => [...left].filter(value => right.has(value));
    const errorMatches = intersects(concepts, errors);
    const planMatches = intersects(concepts, plans);
    const due = dueDays > 0 ? Math.min(WEIGHTS.due_cap, WEIGHTS.due_base + dueDays * WEIGHTS.due_per_day) : 0;
    const breakdown = {
      due_review: round4(due), mastery_gap: round4((1 - mastery) * WEIGHTS.mastery_gap),
      error_match: errorMatches.length ? WEIGHTS.error_match : 0,
      exam_urgency: context.exam_days_remaining !== null && context.exam_days_remaining !== undefined
        && Number(context.exam_days_remaining) >= 0 && Number(context.exam_days_remaining) <= 7 ? WEIGHTS.exam_urgent : 0,
      plan_match: planMatches.length ? WEIGHTS.plan_match : 0,
      novelty: exposures === 0 ? WEIGHTS.novelty : 0,
      repeat_penalty: -Math.min(WEIGHTS.repeat_cap, exposures * WEIGHTS.repeat_each),
    };
    const total = round4(Object.values(breakdown).reduce((sum, value) => sum + value, 0));
    let kind; let explanation;
    if (dueDays > 0) [kind, explanation] = ['due_review', `已逾期 ${dueDays} 天，优先安排复习`];
    else if (errorMatches.length) [kind, explanation] = ['error_correction', `针对最近错因巩固 ${errorMatches.sort().join('、')}`];
    else if (planMatches.length) [kind, explanation] = ['plan_task', `匹配今日计划知识点 ${planMatches.sort().join('、')}`];
    else if (mastery < 0.6) [kind, explanation] = ['weakness_repair', `当前掌握度 ${Math.round(mastery * 100)}%，建议优先补强`];
    else [kind, explanation] = ['coverage', '用于保持题型与知识点覆盖'];
    return { ...candidate, recommendation_type: kind, score_breakdown: breakdown,
      total_score: total, explanation, rule_version: RULE_VERSION };
  });
  scored.sort((a, b) => {
    if (a.total_score !== b.total_score) return b.total_score - a.total_score;
    if (Number(a.due_days || 0) !== Number(b.due_days || 0)) return Number(b.due_days || 0) - Number(a.due_days || 0);
    if (Number(a.mastery_score ?? 0.5) !== Number(b.mastery_score ?? 0.5)) return Number(a.mastery_score ?? 0.5) - Number(b.mastery_score ?? 0.5);
    if (Number(a.recent_exposures || 0) !== Number(b.recent_exposures || 0)) return Number(a.recent_exposures || 0) - Number(b.recent_exposures || 0);
    const aid = stableId(a.question_id); const bid = stableId(b.question_id);
    return aid[0] !== bid[0] ? aid[0] - bid[0] : (aid[1] < bid[1] ? -1 : aid[1] > bid[1] ? 1 : 0);
  });
  return scored.slice(0, Math.max(0, Number(limit)));
}

function localDateAt(value, timezone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function addDateDays(value, days) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function dateDiff(left, right) {
  return Math.max(0, Math.round((new Date(`${right}T00:00:00Z`) - new Date(`${left}T00:00:00Z`)) / 86400000));
}

function buildPlan({ exam_date, daily_minutes, timezone, evaluated_at, due_reviews, weak_concepts }) {
  const minutes = Number(daily_minutes);
  if (minutes < 10 || minutes > 480) throw new Error('daily_minutes must be between 10 and 480');
  const today = localDateAt(evaluated_at, timezone);
  const totalDays = dateDiff(today, exam_date);
  const result = { status: totalDays > 0 ? 'active' : 'expired', exam_date, daily_minutes: minutes,
    timezone, total_days: totalDays, days: [], rule_version: RULE_VERSION };
  if (!totalDays) return result;
  const queue = (due_reviews || []).map(item => ({
    type: 'due_review', concept: item.concept,
    estimated_minutes: Math.max(1, Number(item.estimated_minutes || 5)), reason: '该知识点已到复习时间',
  }));
  queue.push(...[...(weak_concepts || [])].sort((a, b) => Number(a.mastery_score ?? 0.5) - Number(b.mastery_score ?? 0.5) || String(a.concept).localeCompare(String(b.concept))).map(item => ({
    type: 'weakness_repair', concept: item.concept,
    estimated_minutes: Math.max(1, Number(item.estimated_minutes || 10)), reason: '优先补强低掌握度知识点',
  })));
  for (let index = 0; index < totalDays; index += 1) {
    let used = 0; const tasks = [];
    while (queue.length && used + queue[0].estimated_minutes <= minutes) {
      const task = queue.shift(); tasks.push(task); used += task.estimated_minutes;
    }
    result.days.push({ date: addDateDays(today, index), estimated_minutes: used, tasks });
  }
  return result;
}

function summarizeConversation({ messages, known_concepts }) {
  const joined = messages.map(item => String(item.content || '')).join('\n');
  const concepts = known_concepts.filter(concept => joined.includes(concept));
  const studentUnderstanding = []; const misconceptions = []; const unresolved = []; const hints = [];
  for (const item of messages) {
    const text = String(item.content || '').trim(); const reference = { text, message_id: item.id };
    if (item.role === 'user') {
      if (['我理解', '我认为', '我的理解'].some(marker => text.includes(marker))) studentUnderstanding.push(reference);
      if (text.includes('?') || text.includes('？')) unresolved.push(reference);
      if (['误以为', '是不是等于', '我一直以为'].some(marker => text.includes(marker))) misconceptions.push(reference);
    } else if (item.role === 'assistant' && text) hints.push(reference);
  }
  let nextActions;
  if (concepts.includes('栈') && concepts.includes('递归')) nextActions = ['复习栈与递归调用帧的关系'];
  else if (concepts.length) nextActions = [`复习${concepts[0]}并完成一道对应练习`];
  else nextActions = ['整理本次问题并完成一道相关练习'];
  return { concepts, student_understanding: studentUnderstanding, misconceptions,
    unresolved_questions: unresolved, key_hints: hints, next_actions: nextActions,
    generation_method: 'rule', rule_version: RULE_VERSION };
}

module.exports = {
  RULE_VERSION, resolveConcepts, updateMastery, scheduleReview, classifyError,
  scoreRecommendations, buildPlan, summarizeConversation,
};
