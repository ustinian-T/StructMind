"""Application service that turns one answer into a complete learning event."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.learning.contracts import RULE_VERSION
from src.learning.rules import (
    classify_error,
    resolve_concepts,
    schedule_review,
    score_recommendations,
    update_mastery,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _curated_concepts(question: Any) -> list[str]:
    value = getattr(question, "concepts", None) or getattr(question, "knowledge_points", None) or []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def question_concepts(question: Any) -> list[dict[str, Any]]:
    return resolve_concepts(
        str(getattr(question, "stem", "")),
        str(getattr(question, "chapter", "") or ""),
        _curated_concepts(question),
    )


def _state_map(db: Any, user_id: int) -> dict[str, dict[str, Any]]:
    return {row["concept"]: row for row in db.get_concept_mastery(user_id)}


def recommendation_candidates(bank: Any, db: Any, user_id: int) -> list[dict[str, Any]]:
    states = _state_map(db, user_id)
    with db.connect() as connection:
        exposure_rows = connection.execute(
            """SELECT question_id, COUNT(*) AS count FROM attempts
               WHERE user_id = ? AND source = ? GROUP BY question_id""",
            (int(user_id), str(bank.bank_id)),
        ).fetchall()
    exposures = {int(row["question_id"]): int(row["count"]) for row in exposure_rows}
    candidates = []
    for question in bank.questions:
        concepts = question_concepts(question)
        scores = [float(states[item["concept"]]["mastery_score"])
                  for item in concepts if item["concept"] in states]
        candidates.append({
            "question_id": question.id,
            "bank_id": bank.bank_id,
            "concepts": [item["concept"] for item in concepts],
            "mastery_score": min(scores) if scores else 0.5,
            "due_days": 0,
            "recent_exposures": exposures.get(int(question.id), 0),
            "evidence_refs": [f"concept:{item['concept']}" for item in concepts],
        })
    return candidates


class LearningLoopService:
    def __init__(self, db: Any, bank: Any) -> None:
        self.db = db
        self.bank = bank

    def submit_answer(
        self,
        *,
        user_id: int,
        question: Any,
        answer: Any,
        grading: dict[str, Any],
        attempt_token: str,
        session_id: str | None = None,
        time_spent_seconds: float = 0,
        evaluated_at: str | None = None,
    ) -> dict[str, Any]:
        evaluated_at = evaluated_at or utc_now()
        concepts = question_concepts(question)
        states = _state_map(self.db, user_id)
        mastery_changes = []
        for item in concepts:
            current = states.get(item["concept"], {})
            change = update_mastery(
                item["concept"], item["role"], item["weight"], current, grading["is_correct"],
            )
            change["review"] = schedule_review(
                current, grading["is_correct"], item["weight"], evaluated_at,
            )
            mastery_changes.append(change)

        primary_state = states.get(concepts[0]["concept"], {}) if concepts else {}
        error_reason = classify_error(
            grading["is_correct"], question.qtype, answer, question.answer,
            time_spent_seconds, primary_state.get("mastery_score", 0.5),
        )
        candidates = [item for item in recommendation_candidates(self.bank, self.db, user_id)
                      if int(item["question_id"]) != int(question.id)]
        recommendations = score_recommendations(
            candidates,
            {
                "recent_error_concepts": [] if grading["is_correct"] else [item["concept"] for item in concepts],
                "plan_concepts": [],
                "exam_days_remaining": None,
            },
            1,
        )
        draft = {
            "user_id": user_id,
            "question_id": question.id,
            "bank_id": self.bank.bank_id,
            "session_id": session_id,
            "attempt_token": attempt_token,
            "answer": answer,
            "normalized_answer": str(answer or "").strip(),
            "correct_answer": question.answer,
            "is_correct": grading["is_correct"],
            "qtype": question.qtype,
            "chapter": getattr(question, "chapter", "") or "",
            "time_spent_seconds": time_spent_seconds,
            "concept_weights": concepts,
            "evaluated_at": evaluated_at,
            "rule_version": RULE_VERSION,
        }
        outcome = {
            "grading": grading,
            "mastery_changes": mastery_changes,
            "error_reason": error_reason,
            "next_recommendation": recommendations[0] if recommendations else None,
            "enhancement_status": "rule_only",
        }
        return self.db.commit_learning_event(draft, outcome)

    def record_review_feedback(
        self,
        *,
        user_id: int,
        concept: str,
        feedback: str,
        learning_event_id: str | None,
        reviewed_at: str | None = None,
    ) -> dict[str, Any]:
        reviewed_at = reviewed_at or utc_now()
        state = _state_map(self.db, user_id).get(concept)
        if not state:
            raise KeyError("知识点复习状态不存在。")
        review = schedule_review(state, True, 1.0, reviewed_at, feedback)
        return self.db.save_review_feedback(
            user_id, concept, feedback, learning_event_id, reviewed_at, review["next_review_at"],
        )
