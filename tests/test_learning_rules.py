import json
from pathlib import Path

import pytest

from src.learning.rules import (
    build_plan,
    classify_error,
    resolve_concepts,
    schedule_review,
    score_recommendations,
    summarize_conversation,
    update_mastery,
)


VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "learning_loop_vectors.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", VECTORS["mastery"], ids=lambda case: case["name"])
def test_mastery_vectors(case):
    assert update_mastery(**case["input"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["reviews"], ids=lambda case: case["name"])
def test_review_vectors(case):
    assert schedule_review(**case["input"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["errors"], ids=lambda case: case["name"])
def test_error_vectors(case):
    assert classify_error(**case["input"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["recommendations"], ids=lambda case: case["name"])
def test_recommendation_vectors(case):
    result = score_recommendations(**case["input"])
    assert [item["question_id"] for item in result] == case["expected_question_ids"]
    assert all(item["score_breakdown"] and item["explanation"] for item in result)


@pytest.mark.parametrize("case", VECTORS["plans"], ids=lambda case: case["name"])
def test_plan_vectors(case):
    assert build_plan(**case["input"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["summaries"], ids=lambda case: case["name"])
def test_summary_vectors(case):
    assert summarize_conversation(**case["input"]) == case["expected"]


def test_concept_fallback_always_returns_a_primary():
    assert resolve_concepts("无法命中词典", "第九章", []) == [
        {
            "concept": "第九章",
            "role": "primary",
            "weight": 1.0,
            "source": "chapter_fallback",
            "confidence": 0.4,
        }
    ]


def test_primary_and_secondary_weights_are_normalized():
    assert resolve_concepts("二叉树递归遍历", "树", ["二叉树遍历", "递归"]) == [
        {
            "concept": "二叉树遍历",
            "role": "primary",
            "weight": 0.7,
            "source": "curated",
            "confidence": 1.0,
        },
        {
            "concept": "递归",
            "role": "secondary",
            "weight": 0.3,
            "source": "curated",
            "confidence": 1.0,
        },
    ]
