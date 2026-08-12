"""SQLite persistence boundary for atomic learning-loop events."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any

from src.db.database import PracticeDatabase
from src.learning.contracts import REVIEW_FEEDBACK


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _epoch(iso_value: str) -> float:
    return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).timestamp()


class LearningRepository:
    """Persist and retrieve complete, owner-scoped learning events."""

    def __init__(self, database: PracticeDatabase) -> None:
        self.database = database

    def commit_learning_event(self, draft: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
        user_id = int(draft["user_id"])
        attempt_token = str(draft["attempt_token"]).strip()
        if not attempt_token:
            raise ValueError("attempt_token 不能为空")

        with self.database.connect() as connection:
            existing = connection.execute(
                """SELECT response_json FROM learning_events
                   WHERE user_id = ? AND attempt_token = ? AND status = 'committed'""",
                (user_id, attempt_token),
            ).fetchone()
            if existing and existing["response_json"]:
                return json.loads(existing["response_json"])

            event_id = str(uuid.uuid4())
            created_at = str(draft["evaluated_at"])
            error_reason = outcome["error_reason"]
            connection.execute(
                """INSERT INTO attempts
                   (question_id, source, qtype, user_answer, correct_answer,
                    is_correct, created_at, user_id, chapter)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(draft["question_id"]),
                    str(draft["bank_id"]),
                    str(draft.get("qtype") or ""),
                    _json(draft.get("answer")),
                    str(draft.get("correct_answer") or ""),
                    1 if draft.get("is_correct") else 0,
                    _epoch(created_at),
                    user_id,
                    str(draft.get("chapter") or ""),
                ),
            )
            connection.execute(
                """INSERT INTO learning_events
                   (id, user_id, question_id, bank_id, session_id, attempt_token,
                    answer_json, normalized_answer, correct_answer, is_correct, qtype,
                    chapter, time_spent_seconds, concept_weights_json,
                    error_reason_rule_json, error_reason_final_json, rule_version,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    event_id,
                    user_id,
                    int(draft["question_id"]),
                    str(draft["bank_id"]),
                    draft.get("session_id"),
                    attempt_token,
                    _json(draft.get("answer")),
                    str(draft.get("normalized_answer") or ""),
                    str(draft.get("correct_answer") or ""),
                    1 if draft.get("is_correct") else 0,
                    str(draft.get("qtype") or ""),
                    str(draft.get("chapter") or ""),
                    float(draft.get("time_spent_seconds") or 0),
                    _json(draft.get("concept_weights") or []),
                    _json(error_reason),
                    _json(error_reason),
                    str(draft["rule_version"]),
                    created_at,
                ),
            )

            review_updates = []
            for change in outcome.get("mastery_changes") or []:
                review = change["review"]
                connection.execute(
                    """INSERT INTO mastery_changes
                       (learning_event_id, user_id, concept, role, weight,
                        before_score, after_score, delta,
                        before_stability, after_stability,
                        before_difficulty, after_difficulty,
                        evidence_json, next_review_at, rule_version, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        user_id,
                        change["concept"],
                        change["role"],
                        float(change["weight"]),
                        float(change["before_score"]),
                        float(change["after_score"]),
                        float(change["delta"]),
                        float(review["before_stability"]),
                        float(review["after_stability"]),
                        float(review["before_difficulty"]),
                        float(review["after_difficulty"]),
                        _json({
                            "is_correct": bool(draft.get("is_correct")),
                            "role": change["role"],
                            "weight": change["weight"],
                            "qtype": draft.get("qtype"),
                            "error_reason": error_reason,
                            "alpha": change.get("alpha"),
                        }),
                        review["next_review_at"],
                        draft["rule_version"],
                        created_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO concept_mastery
                       (user_id, concept, mastery_score, total_attempts, correct_attempts,
                        last_review_at, next_review_at, stability, difficulty,
                        created_at, updated_at, review_state, last_learning_event_id, rule_version)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, concept) DO UPDATE SET
                        mastery_score = excluded.mastery_score,
                        total_attempts = excluded.total_attempts,
                        correct_attempts = excluded.correct_attempts,
                        last_review_at = excluded.last_review_at,
                        next_review_at = excluded.next_review_at,
                        stability = excluded.stability,
                        difficulty = excluded.difficulty,
                        updated_at = excluded.updated_at,
                        review_state = excluded.review_state,
                        last_learning_event_id = excluded.last_learning_event_id,
                        rule_version = excluded.rule_version""",
                    (
                        user_id,
                        change["concept"],
                        float(change["after_score"]),
                        int(change["total_attempts"]),
                        int(change["correct_attempts"]),
                        created_at,
                        review["next_review_at"],
                        float(review["after_stability"]),
                        float(review["after_difficulty"]),
                        created_at,
                        created_at,
                        review["review_state"],
                        event_id,
                        draft["rule_version"],
                    ),
                )
                review_updates.append({
                    "concept": change["concept"],
                    "role": change["role"],
                    "next_review_at": review["next_review_at"],
                    "interval_days": review["interval_days"],
                    "review_state": review["review_state"],
                })

            recommendation = outcome.get("next_recommendation")
            recommendation_id = None
            if recommendation:
                recommendation_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO recommendation_snapshots
                       (id, user_id, learning_event_id, selected_question_id, bank_id,
                        recommendation_type, score_breakdown_json, evidence_refs_json,
                        student_explanation, total_score, rule_version, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        recommendation_id,
                        user_id,
                        event_id,
                        int(recommendation["question_id"]),
                        recommendation.get("bank_id", "exam"),
                        recommendation["recommendation_type"],
                        _json(recommendation["score_breakdown"]),
                        _json(recommendation.get("evidence_refs") or []),
                        recommendation["explanation"],
                        float(recommendation["total_score"]),
                        recommendation["rule_version"],
                        created_at,
                    ),
                )
                recommendation = {**recommendation, "recommendation_snapshot_id": recommendation_id}

            response = {
                **outcome.get("grading", {}),
                "learning_event_id": event_id,
                "mastery_changes": outcome.get("mastery_changes") or [],
                "error_reason": error_reason,
                "review_updates": review_updates,
                "next_recommendation": recommendation,
                "recommendation_snapshot_id": recommendation_id,
                "plan_progress": outcome.get("plan_progress") or {"status": "not_configured"},
                "enhancement_status": outcome.get("enhancement_status", "rule_only"),
                "rule_version": draft["rule_version"],
            }
            connection.execute(
                """UPDATE learning_events
                   SET recommendation_snapshot_id = ?, response_json = ?, status = 'committed'
                   WHERE id = ? AND status = 'pending'""",
                (recommendation_id, _json(response), event_id),
            )
            return response

    def get_learning_event(self, user_id: int, event_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT response_json FROM learning_events
                   WHERE id = ? AND user_id = ? AND status = 'committed'""",
                (event_id, int(user_id)),
            ).fetchone()
        if not row or not row["response_json"]:
            raise KeyError("学习事件不存在。")
        return json.loads(row["response_json"])

    def get_due_reviews(self, user_id: int, evaluated_at: str) -> list[dict[str, Any]]:
        evaluated_epoch = _epoch(evaluated_at)
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT concept, mastery_score, stability, difficulty, review_state,
                          last_review_at, next_review_at, last_learning_event_id, rule_version
                   FROM concept_mastery
                   WHERE user_id = ? AND (
                     (typeof(next_review_at) = 'text' AND next_review_at <= ?)
                     OR (typeof(next_review_at) != 'text' AND next_review_at <= ?)
                   )
                   ORDER BY next_review_at ASC, mastery_score ASC, concept ASC""",
                (int(user_id), evaluated_at, evaluated_epoch),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_review_feedback(
        self,
        user_id: int,
        concept: str,
        feedback: str,
        learning_event_id: str | None,
        reviewed_at: str,
        next_review_at: str,
    ) -> dict[str, Any]:
        if feedback not in REVIEW_FEEDBACK:
            raise ValueError("复习反馈不合法。")
        feedback_id = str(uuid.uuid4())
        with self.database.connect() as connection:
            state = connection.execute(
                "SELECT id FROM concept_mastery WHERE user_id = ? AND concept = ?",
                (int(user_id), concept),
            ).fetchone()
            if not state:
                raise KeyError("知识点复习状态不存在。")
            connection.execute(
                """INSERT INTO review_feedback
                   (id, user_id, concept, learning_event_id, feedback,
                    reviewed_at, next_review_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id,
                    int(user_id),
                    concept,
                    learning_event_id,
                    feedback,
                    reviewed_at,
                    next_review_at,
                    reviewed_at,
                ),
            )
            connection.execute(
                """UPDATE concept_mastery SET last_review_at = ?, next_review_at = ?, updated_at = ?
                   WHERE user_id = ? AND concept = ?""",
                (reviewed_at, next_review_at, reviewed_at, int(user_id), concept),
            )
        return {
            "id": feedback_id,
            "concept": concept,
            "feedback": feedback,
            "reviewed_at": reviewed_at,
            "next_review_at": next_review_at,
        }
