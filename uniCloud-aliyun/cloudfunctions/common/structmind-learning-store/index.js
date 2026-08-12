// @ts-nocheck
'use strict';

const NAMES = {
  events: 'structmind_learning_events', mastery: 'structmind_concept_mastery',
  changes: 'structmind_mastery_changes', recommendations: 'structmind_recommendation_snapshots',
};

function createLearningStore(db) {
  const events = db.collection(NAMES.events);
  const mastery = db.collection(NAMES.mastery);
  const changes = db.collection(NAMES.changes);
  const recommendations = db.collection(NAMES.recommendations);

  async function eventByToken(userId, attemptToken) {
    const result = await events.where({ user_id: userId, attempt_token: attemptToken }).get();
    return result.data[0] || null;
  }

  async function finish(event) {
    if (event.status === 'committed') return event.response;
    const now = Date.now();
    const outcome = event.outcome || {};
    for (const change of outcome.mastery_changes || []) {
      const exists = await changes.where({ learning_event_id: event._id, concept: change.concept }).get();
      if (!exists.data.length) {
        await changes.add({ ...change, user_id: event.user_id, learning_event_id: event._id, created_at: now });
      }
      const stateResult = await mastery.where({ user_id: event.user_id, concept: change.concept }).get();
      const review = change.review || {};
      const state = {
        mastery_score: change.after_score, total_attempts: change.total_attempts,
        correct_attempts: change.correct_attempts, stability: review.after_stability,
        difficulty: review.after_difficulty, review_state: review.review_state,
        last_review_at: event.draft.evaluated_at, next_review_at: review.next_review_at,
        last_learning_event_id: event._id, rule_version: event.draft.rule_version, updated_at: now,
      };
      if (stateResult.data.length) await mastery.doc(stateResult.data[0]._id).update(state);
      else await mastery.add({ user_id: event.user_id, concept: change.concept, ...state, created_at: now });
    }
    const recommendation = outcome.next_recommendation || (outcome.response || {}).next_recommendation;
    if (recommendation) {
      const found = await recommendations.where({ learning_event_id: event._id }).get();
      if (!found.data.length) {
        await recommendations.add({
          ...recommendation, user_id: event.user_id, learning_event_id: event._id,
          selected_question_id: String(recommendation.question_id), created_at: now, updated_at: now,
        });
      }
    }
    const response = {
      ...(outcome.response || {}), learning_event_id: event._id,
      mastery_changes: outcome.mastery_changes || (outcome.response || {}).mastery_changes || [],
      rule_version: event.draft.rule_version,
    };
    await events.doc(event._id).update({ status: 'committed', response, updated_at: now });
    return response;
  }

  async function commitLearningEvent({ userId, attemptToken, draft, outcome }) {
    if (!String(attemptToken || '').trim()) throw new Error('attempt_token 不能为空');
    let event = await eventByToken(userId, attemptToken);
    if (event && event.status === 'committed') return event.response;
    if (!event) {
      const now = Date.now();
      const added = await events.add({
        user_id: userId, attempt_token: attemptToken, question_id: String(draft.question_id),
        status: 'pending', draft, outcome, rule_version: draft.rule_version,
        created_at: now, updated_at: now,
      });
      event = { _id: added.id, user_id: userId, attempt_token: attemptToken,
        status: 'pending', draft, outcome, created_at: now, updated_at: now };
    }
    return finish(event);
  }

  async function recoverPendingEvent(userId, attemptToken) {
    const event = await eventByToken(userId, attemptToken);
    if (!event) throw new Error('学习事件不存在');
    return finish(event);
  }

  async function getLearningEvent(userId, eventId) {
    const result = await events.doc(eventId).get();
    const event = result.data[0];
    if (!event || event.user_id !== userId || event.status !== 'committed') {
      throw new Error('学习事件不存在');
    }
    return event.response;
  }

  async function getDueReviews(userId, at = Date.now()) {
    const result = await mastery.where({ user_id: userId }).get();
    const instant = typeof at === 'number' ? at : Date.parse(at);
    return result.data.filter(item => Date.parse(item.next_review_at) <= instant)
      .sort((a, b) => Date.parse(a.next_review_at) - Date.parse(b.next_review_at));
  }

  return { commitLearningEvent, recoverPendingEvent, getLearningEvent, getDueReviews };
}

module.exports = { createLearningStore };
