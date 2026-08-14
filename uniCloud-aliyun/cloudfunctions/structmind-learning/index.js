// @ts-nocheck
'use strict';

const db = uniCloud.database();
let rules;
let storeFactory;
try {
  rules = require('structmind-learning-rules');
  storeFactory = require('structmind-learning-store');
} catch (_error) {
  rules = require('../common/structmind-learning-rules');
  storeFactory = require('../common/structmind-learning-store');
}
const store = storeFactory.createLearningStore(db);
const sessions = db.collection('structmind_sessions');
const users = db.collection('structmind_users');
const mastery = db.collection('structmind_concept_mastery');
const feedback = db.collection('structmind_review_feedback');
const plans = db.collection('structmind_learning_plans');
const conversations = db.collection('structmind_ai_conversations');
const summaries = db.collection('structmind_conv_summaries');
const notes = db.collection('structmind_learning_notes');
const questions = db.collection('structmind_questions');
const learningEvents = db.collection('structmind_learning_events');

async function requireAuth(token) {
  if (!token) throw { code: 401, message: '请先登录' };
  const result = await sessions.where({ token }).get();
  const session = result.data[0];
  if (!session || (session.expires_at && session.expires_at <= Date.now())) throw { code: 401, message: '登录已过期' };
  const userResult = await users.doc(session.user_id).get();
  const user = userResult.data[0];
  if (!user || user.status !== 'approved') throw { code: 403, message: '账号未通过审批' };
  return user._id;
}

async function owned(collection, id, userId, message) {
  const result = await collection.doc(id).get();
  const item = result.data[0];
  if (!item || item.user_id !== userId) throw { code: 404, message };
  return item;
}

async function listOwner(collection, userId) {
  return (await collection.where({ user_id: userId }).get()).data;
}

exports.main = async (event) => {
  const { action, params = {} } = event;
  try {
    const userId = await requireAuth(params.token);
    const now = Date.now();
    if (action === 'getEvent') {
      return { code: 0, data: { event: await store.getLearningEvent(userId, params.event_id) } };
    }
    if (action === 'recommend') {
      const questionResult = await questions.limit(200).get();
      const states = await listOwner(mastery, userId);
      const stateMap = new Map(states.map(item => [item.concept, item]));
      const committed = (await listOwner(learningEvents, userId)).filter(item => item.status === 'committed');
      const recentErrors = committed.filter(item => item.response?.is_correct === false)
        .flatMap(item => (item.response?.mastery_changes || []).map(change => change.concept));
      const candidates = questionResult.data.map(question => {
        const concepts = rules.resolveConcepts({ stem: question.content || question.stem || question.title || '',
          chapter: question.chapter || '', curatedConcepts: question.concepts || question.knowledge_points || [] });
        const scores = concepts.map(item => stateMap.get(item.concept)?.mastery_score).filter(Number.isFinite);
        return { question_id: question._id, bank_id: 'exam', concepts: concepts.map(item => item.concept),
          mastery_score: scores.length ? Math.min(...scores) : 0.5, due_days: 0,
          recent_exposures: 0, evidence_refs: concepts.map(item => `concept:${item.concept}`) };
      });
      const recommendations = rules.scoreRecommendations({ candidates,
        context: { recent_error_concepts: recentErrors, plan_concepts: [], exam_days_remaining: null },
        limit: Number(params.count || 10) });
      const byId = new Map(questionResult.data.map(item => [item._id, item]));
      const publicQuestions = recommendations.map(item => {
        const { answer, explanation, ...question } = byId.get(item.question_id);
        return question;
      });
      return { code: 0, data: { questions: publicQuestions, recommendations, count: recommendations.length } };
    }
    if (action === 'getReviews') {
      return { code: 0, data: { reviews: await store.getDueReviews(userId, params.at || now) } };
    }
    if (action === 'reviewFeedback') {
      if (!['too_easy', 'just_right', 'too_hard'].includes(params.feedback)) throw { code: 400, message: '复习反馈不合法' };
      const stateResult = await mastery.where({ user_id: userId, concept: params.concept }).get();
      const state = stateResult.data[0];
      if (!state) throw { code: 404, message: '知识点复习状态不存在' };
      const evaluatedAt = new Date(now).toISOString().replace('.000Z', 'Z');
      const review = rules.scheduleReview({ current: state, is_correct: true, weight: 1,
        evaluated_at: evaluatedAt, feedback: params.feedback });
      const added = await feedback.add({
        user_id: userId, concept: params.concept, feedback: params.feedback,
        learning_event_id: params.learning_event_id || null, reviewed_at: now,
        next_review_at: review.next_review_at, created_at: now, updated_at: now,
      });
      await mastery.doc(state._id).update({ last_review_at: evaluatedAt,
        next_review_at: review.next_review_at, updated_at: now });
      return { code: 0, data: { review_feedback: { _id: added.id, concept: params.concept,
        feedback: params.feedback, next_review_at: review.next_review_at } } };
    }
    if (action === 'savePlan') {
      const evaluatedAt = params.evaluated_at || new Date(now).toISOString().replace('.000Z', 'Z');
      const dailyMinutes = Number(params.daily_minutes);
      if (dailyMinutes < 10 || dailyMinutes > 480) throw { code: 400, message: '每日时长必须在10到480分钟之间' };
      const zone = params.timezone || 'Asia/Shanghai';
      let today;
      try {
        const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' })
          .formatToParts(new Date(evaluatedAt));
        const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
        today = `${values.year}-${values.month}-${values.day}`;
      } catch (_error) { throw { code: 400, message: '未知时区' }; }
      if (String(params.exam_date || '') < today) throw { code: 400, message: '考试日期不能早于今天' };
      const current = await listOwner(plans, userId);
      const version = current.reduce((max, item) => Math.max(max, Number(item.version || 0)), 0) + 1;
      const due = await store.getDueReviews(userId, evaluatedAt);
      const states = await listOwner(mastery, userId);
      const planData = rules.buildPlan({ exam_date: params.exam_date,
        daily_minutes: dailyMinutes, timezone: zone,
        evaluated_at: evaluatedAt, due_reviews: due.map(item => ({ ...item, estimated_minutes: 5 })),
        weak_concepts: states.filter(item => Number(item.mastery_score) < 0.7)
          .map(item => ({ ...item, estimated_minutes: 10 })) });
      for (const plan of current.filter(item => item.status !== 'superseded')) {
        await plans.doc(plan._id).update({ status: 'superseded', updated_at: now });
      }
      const added = await plans.add({ user_id: userId, title: '考试学习计划', chapters: [],
        exam_date: params.exam_date, daily_minutes: dailyMinutes,
        timezone: zone, version, status: planData.status,
        plan_data: planData, created_at: now, updated_at: now });
      return { code: 0, data: { plan: { _id: added.id, version, status: planData.status,
        exam_date: params.exam_date, daily_minutes: dailyMinutes,
        timezone: zone, plan_data: planData } } };
    }
    if (action === 'getPlan') {
      const history = (await listOwner(plans, userId)).sort((a, b) => Number(b.version) - Number(a.version));
      return { code: 0, data: { plan: history.find(item => item.status !== 'superseded') || null, plans: history } };
    }
    if (action === 'summarizeConversation') {
      const conversation = await owned(conversations, params.conversation_id, userId, '对话不存在');
      const messages = (conversation.messages || []).map((item, index) => ({
        ...item, id: item.id || `${conversation._id}:${index + 1}`,
      }));
      const summaryRule = rules.summarizeConversation({ messages,
        known_concepts: ['二叉树遍历', '图的遍历', '递归', '栈', '队列', '哈希', '排序'] });
      const existing = (await summaries.where({ user_id: userId, conversation_id: conversation._id }).get()).data[0];
      const document = { user_id: userId, conversation_id: conversation._id,
        summary_rule: summaryRule, summary_final: summaryRule, generation_method: 'rule',
        rule_version: rules.RULE_VERSION, updated_at: now };
      let id;
      if (existing) { id = existing._id; await summaries.doc(id).update(document); }
      else { const added = await summaries.add({ ...document, created_at: now }); id = added.id; }
      return { code: 0, data: { summary: { _id: id, ...document } } };
    }
    if (action === 'listNotes') {
      let items = await listOwner(notes, userId);
      items = items.filter(item => Boolean(item.is_archived) === Boolean(params.archived));
      if (params.source_type) items = items.filter(item => item.source_type === params.source_type);
      if (params.concept) items = items.filter(item => item.concept === params.concept);
      items.sort((a, b) => Number(b.is_pinned) - Number(a.is_pinned) || b.updated_at - a.updated_at);
      return { code: 0, data: { notes: items } };
    }
    if (action === 'createNote') {
      if (!String(params.title || '').trim()) throw { code: 400, message: '笔记标题不能为空' };
      const document = { user_id: userId, title: String(params.title).trim(), auto_content: null,
        user_content: params.user_content || '', tags: params.tags || [], source_type: 'manual',
        source_id: null, concept: params.concept || null, error_category: null,
        is_pinned: false, is_archived: false, created_at: now, updated_at: now };
      const added = await notes.add(document);
      return { code: 0, data: { note: { _id: added.id, ...document } } };
    }
    if (action === 'updateNote') {
      const note = await owned(notes, params.note_id, userId, '学习笔记不存在');
      const allowed = ['title', 'user_content', 'tags', 'concept', 'is_pinned', 'is_archived'];
      const updates = { updated_at: now };
      for (const key of allowed) if (Object.hasOwn(params, key)) updates[key] = params[key];
      await notes.doc(note._id).update(updates);
      return { code: 0, data: { note: { ...note, ...updates } } };
    }
    return { code: 404, message: `未知操作: ${action}` };
  } catch (error) {
    if (error.code && error.message) return error;
    return { code: 500, message: error.message || '服务器内部错误' };
  }
};
