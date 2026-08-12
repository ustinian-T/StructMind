"""推荐引擎 —— 个性化题目推荐 + 学习计划生成。"""

from __future__ import annotations

import random
from typing import Any

from src.db.database import public_bank_question


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

    with db.connect() as conn:
        recent_ids = {
            row[0]
            for row in conn.execute(
                "SELECT question_id FROM attempts WHERE user_id = ? AND source != 'ai' ORDER BY created_at DESC LIMIT 200",
                (user_id,),
            ).fetchall()
        }

    weak_concepts = set((profile or {}).get("weak_concepts", []))
    type_accuracy = (profile or {}).get("type_accuracy", {})

    def question_score(q) -> float:
        score = 0.0
        if q.chapter in weak_concepts:
            score += 3.0
        if type_accuracy.get(q.qtype, 1.0) < 0.5:
            score += 2.0
        if q.id not in recent_ids:
            score += 1.0
        score += random.uniform(0, 0.5)
        return score

    sorted_questions = sorted(available, key=question_score, reverse=True)
    selected = sorted_questions[:min(requested_count * 2, len(sorted_questions))]
    random.shuffle(selected)
    selected = selected[:requested_count]

    return {
        "questions": [public_bank_question(q) for q in selected],
        "count": len(selected),
        "profile_summary": {
            "weak_concepts": list(weak_concepts),
            "type_accuracy": type_accuracy,
        } if profile else {},
    }


def generate_learning_plan_data(bank, db, user_id: int) -> dict[str, Any]:
    """根据用户画像生成7天学习计划"""
    profile = db.get_user_profile(user_id) or {}
    weak_concepts = profile.get("weak_concepts", [])
    type_accuracy = profile.get("type_accuracy", {})
    weak_types = [t for t, acc in type_accuracy.items() if acc < 0.5]

    daily_targets = {
        "单选题": 10, "多选题": 5, "填空题": 5, "判断题": 5,
    }

    recommendations_by_chapter: dict[str, list[str]] = {}
    for ch, acc in (profile.get("chapter_accuracy", {}) or {}).items():
        if acc < 0.5:
            recommendations_by_chapter[ch] = ["重点复习该章节基础概念", "完成该章节练习并查看解析"]
        elif acc < 0.7:
            recommendations_by_chapter[ch] = ["巩固该章节中等难度题目", "回顾错题中的知识点"]
        else:
            recommendations_by_chapter[ch] = ["保持练习，尝试变体题目"]

    plan_days = []
    for day in range(7):
        day_targets = [
            {"qtype": qtype, "target_count": count, "source": "exam", "completed": 0}
            for qtype, count in daily_targets.items()
        ]
        focus_chapter = (
            weak_concepts[day % len(weak_concepts)]
            if weak_concepts
            else (bank.questions[0].chapter if bank.questions else "未分章")
        )
        plan_days.append({
            "day_index": day,
            "day_label": f"第{day + 1}天",
            "focus_chapter": focus_chapter,
            "focus_types": weak_types[:2] if weak_types else ["单选题", "填空题"],
            "targets": day_targets,
            "recommendations": recommendations_by_chapter.get(
                focus_chapter, ["完成每日练习目标", "回顾当日错题"]
            ),
            "progress": 0,
        })

    return {
        "days": plan_days,
        "total_days": 7,
        "profile_summary": {
            "weak_concepts": weak_concepts,
            "weak_types": weak_types,
            "overall_accuracy": profile.get("accuracy", 0),
        },
    }
