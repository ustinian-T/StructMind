from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.db.database import PracticeDatabase
from src.learning.repository import LearningRepository


@pytest.fixture
def database():
    path = Path(tempfile.mktemp(suffix=".sqlite3"))
    db = PracticeDatabase(path)
    yield db
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def approved_users(database):
    owner = database.create_user("loopowner", "OwnerPass123", "闭环用户", "13800138000")
    other = database.create_user("loopother", "OtherPass123", "其他用户", "13800138001")
    database.approve_user(owner["id"], True)
    database.approve_user(other["id"], True)
    return owner, other


def event_draft(user_id: int, token: str = "attempt-token-001") -> dict:
    return {
        "user_id": user_id,
        "attempt_token": token,
        "question_id": 12,
        "bank_id": "exam",
        "session_id": "session-1",
        "answer": "A",
        "normalized_answer": "A",
        "correct_answer": "B",
        "is_correct": False,
        "qtype": "单选题",
        "chapter": "树",
        "time_spent_seconds": 18,
        "concept_weights": [
            {"concept": "二叉树遍历", "role": "primary", "weight": 0.7},
            {"concept": "递归", "role": "secondary", "weight": 0.3},
        ],
        "evaluated_at": "2026-08-12T00:00:00Z",
        "rule_version": "learning-loop-v1",
    }


def event_outcome() -> dict:
    error = {
        "category": "unclassified",
        "subcategory": "insufficient_evidence",
        "confidence": 0.3,
        "evidence": ["no_specific_rule_matched"],
        "source": "rule",
        "rule_version": "learning-loop-v1",
    }
    return {
        "mastery_changes": [
            {
                "concept": "二叉树遍历",
                "role": "primary",
                "weight": 0.7,
                "before_score": 0.5,
                "after_score": 0.395,
                "delta": -0.105,
                "alpha": 0.3,
                "total_attempts": 1,
                "correct_attempts": 0,
                "review": {
                    "before_stability": 1.0,
                    "after_stability": 0.65,
                    "before_difficulty": 0.3,
                    "after_difficulty": 0.44,
                    "review_state": "relearning",
                    "interval_days": 1,
                    "next_review_at": "2026-08-13T00:00:00Z",
                    "rule_version": "learning-loop-v1",
                },
            },
            {
                "concept": "递归",
                "role": "secondary",
                "weight": 0.3,
                "before_score": 0.5,
                "after_score": 0.455,
                "delta": -0.045,
                "alpha": 0.3,
                "total_attempts": 1,
                "correct_attempts": 0,
                "review": {
                    "before_stability": 1.0,
                    "after_stability": 0.85,
                    "before_difficulty": 0.3,
                    "after_difficulty": 0.36,
                    "review_state": "relearning",
                    "interval_days": 1,
                    "next_review_at": "2026-08-13T00:00:00Z",
                    "rule_version": "learning-loop-v1",
                },
            },
        ],
        "error_reason": error,
        "next_recommendation": {
            "question_id": 18,
            "bank_id": "exam",
            "recommendation_type": "error_correction",
            "score_breakdown": {"mastery_gap": 18.15, "error_match": 20.0},
            "total_score": 38.15,
            "explanation": "针对最近错因巩固二叉树遍历",
            "evidence_refs": ["concept:二叉树遍历"],
            "rule_version": "learning-loop-v1",
        },
        "plan_progress": {"status": "not_configured"},
        "enhancement_status": "rule_only",
        "grading": {
            "is_correct": False,
            "correct_answer": "B",
            "analysis": "答案不匹配，标准答案为 B。",
        },
    }


def test_migration_creates_learning_loop_tables_and_indexes(database):
    database.init()
    with database.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        concept_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(concept_mastery)").fetchall()
        }

    assert {
        "learning_events",
        "question_concepts",
        "mastery_changes",
        "review_feedback",
        "recommendation_snapshots",
        "conversation_summaries",
        "learning_notes",
    }.issubset(tables)
    assert "ux_learning_events_user_attempt_token" in indexes
    assert {"review_state", "last_learning_event_id", "rule_version"}.issubset(concept_columns)


def test_commit_persists_complete_event_and_mastery(database, approved_users):
    owner, _ = approved_users
    repository = LearningRepository(database)

    result = repository.commit_learning_event(event_draft(owner["id"]), event_outcome())

    assert result["learning_event_id"]
    assert result["recommendation_snapshot_id"]
    assert len(result["mastery_changes"]) == 2
    stored = repository.get_learning_event(owner["id"], result["learning_event_id"])
    assert stored == result
    with database.connect() as conn:
        mastery = conn.execute(
            "SELECT * FROM concept_mastery WHERE user_id = ? ORDER BY concept",
            (owner["id"],),
        ).fetchall()
        changes = conn.execute(
            "SELECT * FROM mastery_changes WHERE learning_event_id = ?",
            (result["learning_event_id"],),
        ).fetchall()
        attempt_count = conn.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ?", (owner["id"],)
        ).fetchone()[0]
    assert len(mastery) == 2
    assert len(changes) == 2
    assert attempt_count == 1
    assert {row["last_learning_event_id"] for row in mastery} == {result["learning_event_id"]}


def test_duplicate_attempt_token_replays_original_without_new_changes(database, approved_users):
    owner, _ = approved_users
    repository = LearningRepository(database)
    draft = event_draft(owner["id"])

    first = repository.commit_learning_event(draft, event_outcome())
    changed_outcome = event_outcome()
    changed_outcome["grading"]["analysis"] = "不应覆盖首次响应"
    second = repository.commit_learning_event(draft, changed_outcome)

    assert second == first
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mastery_changes").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_recommendation_failure_rolls_back_event_and_mastery(database, approved_users):
    owner, _ = approved_users
    repository = LearningRepository(database)
    with database.connect() as conn:
        conn.execute(
            """CREATE TRIGGER reject_recommendation BEFORE INSERT ON recommendation_snapshots
               BEGIN SELECT RAISE(ABORT, 'forced recommendation failure'); END"""
        )

    with pytest.raises(Exception, match="forced recommendation failure"):
        repository.commit_learning_event(event_draft(owner["id"]), event_outcome())

    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM mastery_changes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM concept_mastery").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_event_trace_is_scoped_to_owner(database, approved_users):
    owner, other = approved_users
    repository = LearningRepository(database)
    result = repository.commit_learning_event(event_draft(owner["id"]), event_outcome())

    with pytest.raises(KeyError, match="学习事件不存在"):
        repository.get_learning_event(other["id"], result["learning_event_id"])


def test_due_reviews_and_feedback_are_owner_scoped(database, approved_users):
    owner, other = approved_users
    repository = LearningRepository(database)
    result = repository.commit_learning_event(event_draft(owner["id"]), event_outcome())

    due = repository.get_due_reviews(owner["id"], "2026-08-14T00:00:00Z")
    assert [item["concept"] for item in due] == ["二叉树遍历", "递归"]
    assert repository.get_due_reviews(other["id"], "2026-08-14T00:00:00Z") == []

    feedback = repository.save_review_feedback(
        owner["id"], "二叉树遍历", "too_hard", result["learning_event_id"],
        "2026-08-14T00:00:00Z", "2026-08-15T00:00:00Z",
    )
    assert feedback["feedback"] == "too_hard"
    with pytest.raises(KeyError, match="知识点复习状态不存在"):
        repository.save_review_feedback(
            other["id"], "二叉树遍历", "just_right", result["learning_event_id"],
            "2026-08-14T00:00:00Z", "2026-08-16T00:00:00Z",
        )
