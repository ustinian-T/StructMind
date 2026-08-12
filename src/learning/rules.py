"""Pure, versioned rules used by every learning-loop runtime."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import RECOMMENDATION_WEIGHTS, REVIEW_FEEDBACK, RULE_VERSION


CONCEPT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("二叉树遍历", ("二叉树", "遍历")),
    ("图的遍历", ("图", "遍历")),
    ("递归", ("递归", "调用栈")),
    ("栈", ("栈", "后进先出")),
    ("队列", ("队列", "先进先出")),
    ("哈希", ("哈希", "散列")),
    ("排序", ("排序", "快排", "归并")),
)


def _round4(value: float) -> float:
    return round(float(value) + 0.0, 4)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_concepts(stem: str, chapter: str, curated_concepts: list[str]) -> list[dict[str, Any]]:
    """Resolve one primary and optional secondary concepts with normalized weights."""
    ordered: list[tuple[str, str, float]] = []
    for concept in curated_concepts:
        normalized = str(concept).strip()
        if normalized and normalized not in {item[0] for item in ordered}:
            ordered.append((normalized, "curated", 1.0))

    if not ordered:
        for concept, keywords in CONCEPT_KEYWORDS:
            if any(keyword in stem for keyword in keywords):
                ordered.append((concept, "keyword_rule", 0.75))

    if not ordered:
        fallback = chapter.strip() or "未分章"
        return [{
            "concept": fallback,
            "role": "primary",
            "weight": 1.0,
            "source": "chapter_fallback",
            "confidence": 0.4,
        }]

    primary_weight = 1.0 if len(ordered) == 1 else 0.7
    secondary_weight = _round4((1.0 - primary_weight) / max(1, len(ordered) - 1))
    result = []
    for index, (concept, source, confidence) in enumerate(ordered):
        result.append({
            "concept": concept,
            "role": "primary" if index == 0 else "secondary",
            "weight": primary_weight if index == 0 else secondary_weight,
            "source": source,
            "confidence": confidence,
        })
    correction = _round4(1.0 - sum(item["weight"] for item in result))
    result[-1]["weight"] = _round4(result[-1]["weight"] + correction)
    return result


def update_mastery(
    concept: str,
    role: str,
    weight: float,
    current: dict[str, Any],
    is_correct: bool,
    consecutive_correct: int = 0,
) -> dict[str, Any]:
    """Apply a stable weighted exponential update and return auditable before/after data."""
    before = float(current.get("mastery_score", 0.5))
    alpha = 0.33 if is_correct and consecutive_correct >= 2 else 0.30
    target = 1.0 if is_correct else 0.0
    after = _round4(_clamp(before + alpha * float(weight) * (target - before)))
    total = int(current.get("total_attempts", 0)) + 1
    correct = int(current.get("correct_attempts", 0)) + (1 if is_correct else 0)
    return {
        "concept": concept,
        "role": role,
        "weight": _round4(weight),
        "before_score": _round4(before),
        "after_score": after,
        "delta": _round4(after - before),
        "alpha": _round4(alpha),
        "total_attempts": total,
        "correct_attempts": correct,
        "rule_version": RULE_VERSION,
    }


def schedule_review(
    current: dict[str, Any],
    is_correct: bool,
    weight: float,
    evaluated_at: str,
    feedback: str | None = None,
) -> dict[str, Any]:
    """Update review stability/difficulty and calculate the next UTC due date."""
    if feedback is not None and feedback not in REVIEW_FEEDBACK:
        raise ValueError("feedback must be too_easy, just_right, or too_hard")
    before_stability = float(current.get("stability", 1.0))
    before_difficulty = float(current.get("difficulty", 0.3))
    weight = _clamp(float(weight))
    if is_correct:
        after_difficulty = _clamp(before_difficulty - 0.1 * weight)
        target_stability = before_stability * (1.0 + 0.5 * (1.0 - after_difficulty))
        after_stability = before_stability + weight * (target_stability - before_stability)
    else:
        after_difficulty = _clamp(before_difficulty + 0.2 * weight)
        target_stability = max(0.5, before_stability * 0.5)
        after_stability = before_stability + weight * (target_stability - before_stability)

    attempts = int(current.get("total_attempts", 0))
    if attempts == 0:
        interval = 3 if is_correct else 1
        state = "learning" if is_correct else "relearning"
    elif not is_correct:
        interval = 1
        state = "relearning"
    else:
        interval = max(1, int(after_stability * (1.0 - after_difficulty) * 7.0))
        state = "review"

    if feedback == "too_easy":
        interval = max(1, int(interval * 1.5))
    elif feedback == "too_hard":
        interval = max(1, int(interval * 0.6))

    evaluated = _parse_utc(evaluated_at)
    return {
        "before_stability": _round4(before_stability),
        "after_stability": _round4(after_stability),
        "before_difficulty": _round4(before_difficulty),
        "after_difficulty": _round4(after_difficulty),
        "review_state": state,
        "interval_days": interval,
        "next_review_at": _format_utc(evaluated + timedelta(days=interval)),
        "rule_version": RULE_VERSION,
    }


def _compact_answer(value: Any) -> str:
    return re.sub(r"[\s,.，。;；:：()（）\[\]【】]+", "", str(value or "")).casefold()


def classify_error(
    is_correct: bool,
    qtype: str,
    user_answer: Any,
    correct_answer: Any,
    time_spent_seconds: int | float | None,
    mastery_score: float | None,
) -> dict[str, Any]:
    """Return a conservative rule classification; never invent evidence."""
    if not is_correct and _compact_answer(user_answer) == _compact_answer(correct_answer):
        category, subcategory, confidence, evidence = (
            "answer_format", "equivalent_after_compaction", 0.95, ["compact_answers_match"]
        )
    elif not is_correct and time_spent_seconds is not None and float(time_spent_seconds) <= 3:
        category, subcategory, confidence, evidence = (
            "guessing", "very_short_response_time", 0.8, ["time_spent_seconds<=3"]
        )
    elif not is_correct and qtype == "多选题":
        user_set = set(re.sub(r"[^A-H]", "", str(user_answer).upper()))
        correct_set = set(re.sub(r"[^A-H]", "", str(correct_answer).upper()))
        if user_set and user_set < correct_set:
            category, subcategory, confidence, evidence = (
                "reading_omission", "missing_required_options", 0.75, ["selected_options_are_subset"]
            )
        else:
            category, subcategory, confidence, evidence = (
                "unclassified", "insufficient_evidence", 0.3, ["no_specific_rule_matched"]
            )
    elif not is_correct and mastery_score is not None and float(mastery_score) < 0.5:
        category, subcategory, confidence, evidence = (
            "concept_gap", "low_prior_mastery", 0.65, ["mastery_score<0.5"]
        )
    else:
        category, subcategory, confidence, evidence = (
            "unclassified", "insufficient_evidence", 0.3, ["no_specific_rule_matched"]
        )
    return {
        "category": category,
        "subcategory": subcategory,
        "confidence": confidence,
        "evidence": evidence,
        "source": "rule",
        "rule_version": RULE_VERSION,
    }


def _stable_question_id(value: Any) -> tuple[int, Any]:
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def score_recommendations(
    candidates: list[dict[str, Any]],
    context: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """Score candidates without randomness and include a student-readable explanation."""
    recent_errors = set(context.get("recent_error_concepts") or [])
    plan_concepts = set(context.get("plan_concepts") or [])
    exam_days = context.get("exam_days_remaining")
    scored = []
    for candidate in candidates:
        concepts = set(candidate.get("concepts") or [])
        due_days = max(0, int(candidate.get("due_days") or 0))
        mastery = _clamp(float(candidate.get("mastery_score", 0.5)))
        exposures = max(0, int(candidate.get("recent_exposures") or 0))
        due = min(
            RECOMMENDATION_WEIGHTS["due_cap"],
            RECOMMENDATION_WEIGHTS["due_base"] + due_days * RECOMMENDATION_WEIGHTS["due_per_day"],
        ) if due_days > 0 else 0.0
        breakdown = {
            "due_review": _round4(due),
            "mastery_gap": _round4((1.0 - mastery) * RECOMMENDATION_WEIGHTS["mastery_gap"]),
            "error_match": RECOMMENDATION_WEIGHTS["error_match"] if concepts & recent_errors else 0.0,
            "exam_urgency": RECOMMENDATION_WEIGHTS["exam_urgent"] if exam_days is not None and 0 <= int(exam_days) <= 7 else 0.0,
            "plan_match": RECOMMENDATION_WEIGHTS["plan_match"] if concepts & plan_concepts else 0.0,
            "novelty": RECOMMENDATION_WEIGHTS["novelty"] if exposures == 0 else 0.0,
            "repeat_penalty": -min(RECOMMENDATION_WEIGHTS["repeat_cap"], exposures * RECOMMENDATION_WEIGHTS["repeat_each"]),
        }
        total = _round4(sum(breakdown.values()))
        if due_days > 0:
            kind = "due_review"
            explanation = f"已逾期 {due_days} 天，优先安排复习"
        elif concepts & recent_errors:
            kind = "error_correction"
            explanation = f"针对最近错因巩固 {'、'.join(sorted(concepts & recent_errors))}"
        elif concepts & plan_concepts:
            kind = "plan_task"
            explanation = f"匹配今日计划知识点 {'、'.join(sorted(concepts & plan_concepts))}"
        elif mastery < 0.6:
            kind = "weakness_repair"
            explanation = f"当前掌握度 {round(mastery * 100)}%，建议优先补强"
        else:
            kind = "coverage"
            explanation = "用于保持题型与知识点覆盖"
        scored.append({
            **candidate,
            "recommendation_type": kind,
            "score_breakdown": breakdown,
            "total_score": total,
            "explanation": explanation,
            "rule_version": RULE_VERSION,
        })
    scored.sort(key=lambda item: (
        -item["total_score"],
        -max(0, int(item.get("due_days") or 0)),
        float(item.get("mastery_score", 0.5)),
        int(item.get("recent_exposures") or 0),
        _stable_question_id(item.get("question_id")),
    ))
    return scored[:max(0, int(limit))]


def _local_date(evaluated_at: str, timezone_name: str) -> date:
    instant = _parse_utc(evaluated_at)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown timezone") from exc
    return instant.astimezone(zone).date()


def build_plan(
    exam_date: str,
    daily_minutes: int,
    timezone: str,
    evaluated_at: str,
    due_reviews: list[dict[str, Any]],
    weak_concepts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a bounded plan up to, but never after, the exam date."""
    if not 10 <= int(daily_minutes) <= 480:
        raise ValueError("daily_minutes must be between 10 and 480")
    today = _local_date(evaluated_at, timezone)
    exam = date.fromisoformat(exam_date)
    total_days = max(0, (exam - today).days)
    base = {
        "status": "active" if total_days > 0 else "expired",
        "exam_date": exam_date,
        "daily_minutes": int(daily_minutes),
        "timezone": timezone,
        "total_days": total_days,
        "days": [],
        "rule_version": RULE_VERSION,
    }
    if total_days == 0:
        return base

    queue = [
        {
            "type": "due_review",
            "concept": item["concept"],
            "estimated_minutes": max(1, int(item.get("estimated_minutes", 5))),
            "reason": "该知识点已到复习时间",
        }
        for item in due_reviews
    ]
    queue.extend({
        "type": "weakness_repair",
        "concept": item["concept"],
        "estimated_minutes": max(1, int(item.get("estimated_minutes", 10))),
        "reason": "优先补强低掌握度知识点",
    } for item in sorted(weak_concepts, key=lambda item: (float(item.get("mastery_score", 0.5)), item["concept"])))

    for day_index in range(total_days):
        used = 0
        tasks = []
        while queue and used + queue[0]["estimated_minutes"] <= int(daily_minutes):
            task = queue.pop(0)
            tasks.append(task)
            used += task["estimated_minutes"]
        base["days"].append({
            "date": (today + timedelta(days=day_index)).isoformat(),
            "estimated_minutes": used,
            "tasks": tasks,
        })
    return base


def summarize_conversation(
    messages: list[dict[str, Any]],
    known_concepts: list[str],
) -> dict[str, Any]:
    """Extract cited facts without converting tutor claims into student mastery."""
    joined = "\n".join(str(item.get("content", "")) for item in messages)
    concepts = [concept for concept in known_concepts if concept in joined]
    student_understanding = []
    misconceptions = []
    unresolved = []
    hints = []
    for item in messages:
        content = str(item.get("content", "")).strip()
        reference = {"text": content, "message_id": item.get("id")}
        if item.get("role") == "user":
            if any(marker in content for marker in ("我理解", "我认为", "我的理解")):
                student_understanding.append(reference)
            if "?" in content or "？" in content:
                unresolved.append(reference)
            if any(marker in content for marker in ("误以为", "是不是等于", "我一直以为")):
                misconceptions.append(reference)
        elif item.get("role") == "assistant" and content:
            hints.append(reference)
    if "栈" in concepts and "递归" in concepts:
        actions = ["复习栈与递归调用帧的关系"]
    elif concepts:
        actions = [f"复习{concepts[0]}并完成一道对应练习"]
    else:
        actions = ["整理本次问题并完成一道相关练习"]
    return {
        "concepts": concepts,
        "student_understanding": student_understanding,
        "misconceptions": misconceptions,
        "unresolved_questions": unresolved,
        "key_hints": hints,
        "next_actions": actions,
        "generation_method": "rule",
        "rule_version": RULE_VERSION,
    }
