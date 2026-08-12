"""Shared constants for the Python and uniCloud learning-loop implementations."""

from __future__ import annotations

RULE_VERSION = "learning-loop-v1"

ERROR_CATEGORIES = frozenset({
    "concept_gap",
    "method_selection",
    "reasoning_step",
    "calculation_operation",
    "reading_omission",
    "memory_confusion",
    "answer_format",
    "guessing",
    "unclassified",
})

REVIEW_FEEDBACK = frozenset({"too_easy", "just_right", "too_hard"})
REVIEW_STATES = frozenset({"new", "learning", "review", "relearning"})

RECOMMENDATION_WEIGHTS = {
    "due_base": 20.0,
    "due_per_day": 5.0,
    "due_cap": 40.0,
    "mastery_gap": 30.0,
    "error_match": 20.0,
    "exam_urgent": 10.0,
    "plan_match": 10.0,
    "novelty": 5.0,
    "repeat_each": 5.0,
    "repeat_cap": 20.0,
}
