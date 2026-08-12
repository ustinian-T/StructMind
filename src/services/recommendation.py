"""推荐引擎 —— 个性化题目推荐 + 学习计划生成。"""

from __future__ import annotations

from datetime import date, datetime, timezone as utc_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.db.database import public_bank_question
from src.learning.rules import score_recommendations
from src.learning.service import recommendation_candidates


def recommend_questions(
    bank, db, profile: dict[str, Any] | None, user_id: int, payload: dict[str, Any],
) -> dict[str, Any]:
    requested_count = int(payload.get("count") or 10)
    qtypes = payload.get("types") or []
    if not qtypes:
        qtypes = ["单选题", "多选题", "填空题", "判断题"]

    available = [q for q in bank.questions if (not qtypes or q.qtype in qtypes)]
    if not available:
        return {"questions": [], "reason": "没有符合条件的题目。"}

    weak_concepts = set((profile or {}).get("weak_concepts", []))
    type_accuracy = (profile or {}).get("type_accuracy", {})
    allowed_ids = {int(question.id) for question in available}
    candidates = [item for item in recommendation_candidates(bank, db, user_id)
                  if int(item["question_id"]) in allowed_ids]
    recommendations = score_recommendations(
        candidates,
        {"recent_error_concepts": list(weak_concepts), "plan_concepts": [],
         "exam_days_remaining": None},
        requested_count,
    )
    by_id = {int(question.id): question for question in available}
    selected = [by_id[int(item["question_id"])] for item in recommendations]

    return {
        "questions": [public_bank_question(q) for q in selected],
        "recommendations": recommendations,
        "count": len(selected),
        "profile_summary": {
            "weak_concepts": list(weak_concepts),
            "type_accuracy": type_accuracy,
        } if profile else {},
    }


def generate_learning_plan_data(
    bank, db, user_id: int, *, exam_date: str, daily_minutes: int,
    timezone: str, evaluated_at: str,
) -> dict[str, Any]:
    """根据考试日期、时间预算、到期复习和薄弱知识点生成计划。"""
    from src.learning.rules import build_plan

    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("未知时区。") from exc
    instant = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=utc_timezone.utc)
    if date.fromisoformat(exam_date) < instant.astimezone(zone).date():
        raise ValueError("考试日期不能早于今天。")

    profile = db.get_user_profile(user_id) or {}
    mastery = db.get_concept_mastery(user_id)
    weak = [{"concept": item["concept"], "mastery_score": item["mastery_score"],
             "estimated_minutes": 10} for item in mastery if item["mastery_score"] < 0.7]
    for concept in profile.get("weak_concepts", []):
        if concept not in {item["concept"] for item in weak}:
            weak.append({"concept": concept, "mastery_score": 0.5, "estimated_minutes": 10})
    due = [{**item, "estimated_minutes": 5} for item in db.get_due_reviews(user_id, evaluated_at)]
    return build_plan(exam_date, daily_minutes, timezone, evaluated_at, due, weak)
