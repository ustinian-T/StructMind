from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.db.database import PracticeDatabase
from src.models import ObjectiveQuestion
from src.routes.learning import router as learning_router
from src.routes.practice import router as practice_router


class Bank:
    bank_id = "exam"

    def __init__(self):
        self.questions = [
            ObjectiveQuestion(
                id=1, source_order=1, source_num="1", qtype="单选题", chapter="栈和队列",
                stem="栈的主要特征是什么？", options=[
                    {"key": "A", "text": "先进先出"}, {"key": "B", "text": "后进先出"},
                ], answer="B", raw_correct="B", score=2,
            ),
            ObjectiveQuestion(
                id=2, source_order=2, source_num="2", qtype="单选题", chapter="栈和队列",
                stem="队列的主要特征是什么？", options=[
                    {"key": "A", "text": "先进先出"}, {"key": "B", "text": "后进先出"},
                ], answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=3, source_order=3, source_num="3", qtype="判断题", chapter="栈和队列",
                stem="递归调用通常使用栈保存调用现场。", options=[
                    {"key": "A", "text": "对"}, {"key": "B", "text": "错"},
                ], answer="A", raw_correct="A", score=1,
            ),
        ]
        self.by_id = {question.id: question for question in self.questions}


class EmptyAssignmentBank:
    bank_id = "assignment"
    questions = []
    by_id = {}


@pytest.fixture
def api_context():
    path = Path(tempfile.mktemp(suffix=".sqlite3"))
    database = PracticeDatabase(path)
    owner = database.create_user("apiowner", "OwnerPass123", "接口用户", "13800138000")
    other = database.create_user("apiother", "OtherPass123", "其他用户", "13800138001")
    database.approve_user(owner["id"], True)
    database.approve_user(other["id"], True)
    owner_token = database.create_session(owner["id"])
    other_token = database.create_session(other["id"])

    app = FastAPI()
    app.state.db = database
    app.state.exam_bank = Bank()
    app.state.assignment_bank = EmptyAssignmentBank()
    app.state._json_response = lambda body, status=200: JSONResponse(body, status_code=status)
    app.include_router(practice_router, prefix="/api")
    app.include_router(learning_router, prefix="/api")
    with TestClient(app) as client:
        yield client, database, owner_token, other_token
    try:
        os.remove(path)
    except OSError:
        pass


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_authenticated_answer_returns_complete_traceable_loop(api_context):
    client, database, owner_token, _ = api_context

    response = client.post(
        "/api/answer",
        headers=auth(owner_token),
        json={
            "question_id": 1,
            "answer": "A",
            "attempt_token": "web-question-1-attempt-1",
            "session_id": "web-session-1",
            "time_spent_seconds": 16,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_correct"] is False
    assert body["learning_event_id"]
    assert len(body["mastery_changes"]) >= 1
    assert all({"before_score", "after_score", "delta", "weight"} <= change.keys()
               for change in body["mastery_changes"])
    assert body["error_reason"]["source"] == "rule"
    assert body["review_updates"][0]["next_review_at"]
    assert body["next_recommendation"]["explanation"]
    assert body["recommendation_snapshot_id"]
    assert body["enhancement_status"] == "rule_only"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_authenticated_answer_requires_attempt_token(api_context):
    client, _, owner_token, _ = api_context
    response = client.post(
        "/api/answer", headers=auth(owner_token), json={"question_id": 1, "answer": "B"},
    )
    assert response.status_code == 400
    assert "attempt_token" in response.json()["error"]


def test_duplicate_answer_token_replays_same_event(api_context):
    client, database, owner_token, _ = api_context
    payload = {"question_id": 1, "answer": "A", "attempt_token": "retry-token-1"}

    first = client.post("/api/answer", headers=auth(owner_token), json=payload).json()
    second = client.post("/api/answer", headers=auth(owner_token), json=payload).json()

    assert second == first
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0] == 1


def test_anonymous_answer_keeps_legacy_grading_without_user_loop(api_context):
    client, database, _, _ = api_context
    response = client.post("/api/answer", json={"question_id": 1, "answer": "B"})

    assert response.status_code == 200
    assert response.json()["is_correct"] is True
    assert "learning_event_id" not in response.json()
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0] == 0


def test_event_trace_endpoint_enforces_ownership(api_context):
    client, _, owner_token, other_token = api_context
    answer = client.post(
        "/api/answer",
        headers=auth(owner_token),
        json={"question_id": 1, "answer": "A", "attempt_token": "trace-token-1"},
    ).json()

    owner_response = client.get(
        f"/api/learning/events/{answer['learning_event_id']}", headers=auth(owner_token),
    )
    other_response = client.get(
        f"/api/learning/events/{answer['learning_event_id']}", headers=auth(other_token),
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["event"]["learning_event_id"] == answer["learning_event_id"]
    assert other_response.status_code == 404


def test_recommendations_are_deterministic_and_explainable(api_context):
    client, _, owner_token, _ = api_context
    client.post(
        "/api/answer",
        headers=auth(owner_token),
        json={"question_id": 1, "answer": "A", "attempt_token": "recommend-seed-1"},
    )
    payload = {"count": 3, "types": ["单选题", "判断题"], "bank_id": "exam"}

    first = client.post("/api/recommend/questions", headers=auth(owner_token), json=payload).json()
    second = client.post("/api/recommend/questions", headers=auth(owner_token), json=payload).json()

    assert [item["id"] for item in first["questions"]] == [item["id"] for item in second["questions"]]
    assert first["recommendations"] == second["recommendations"]
    assert all(item["score_breakdown"] and item["explanation"]
               for item in first["recommendations"])


def test_due_review_queue_and_feedback_endpoint(api_context):
    client, _, owner_token, _ = api_context
    answer = client.post(
        "/api/answer",
        headers=auth(owner_token),
        json={"question_id": 1, "answer": "A", "attempt_token": "review-seed-1"},
    ).json()

    due = client.get("/api/learning/reviews?at=2030-01-01T00:00:00Z", headers=auth(owner_token))
    assert due.status_code == 200
    assert due.json()["reviews"]
    concept = due.json()["reviews"][0]["concept"]

    feedback = client.post(
        "/api/learning/reviews/feedback",
        headers=auth(owner_token),
        json={
            "concept": concept,
            "feedback": "too_hard",
            "learning_event_id": answer["learning_event_id"],
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["review_feedback"]["feedback"] == "too_hard"
