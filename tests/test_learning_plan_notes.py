from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
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
        self.questions = [ObjectiveQuestion(
            id=1, source_order=1, source_num="1", qtype="单选题", chapter="栈和队列",
            stem="栈的主要特征是什么？", options=[
                {"key": "A", "text": "先进先出"}, {"key": "B", "text": "后进先出"},
            ], answer="B", raw_correct="B", score=2,
        )]
        self.by_id = {1: self.questions[0]}


class EmptyBank:
    bank_id = "assignment"
    questions = []
    by_id = {}


@pytest.fixture
def context():
    path = Path(tempfile.mktemp(suffix=".sqlite3"))
    db = PracticeDatabase(path)
    user = db.create_user("planner", "PlanPass123", "计划用户", "13800138111")
    db.approve_user(user["id"], True)
    token = db.create_session(user["id"])
    app = FastAPI()
    app.state.db = db
    app.state.exam_bank = Bank()
    app.state.assignment_bank = EmptyBank()
    app.state._json_response = lambda body, status=200: JSONResponse(body, status_code=status)
    app.include_router(practice_router, prefix="/api")
    app.include_router(learning_router, prefix="/api")
    with TestClient(app) as client:
        yield client, db, user["id"], {"Authorization": f"Bearer {token}"}
    try:
        os.remove(path)
    except OSError:
        pass


def test_exam_plan_is_bounded_and_versioned(context):
    client, _, _, headers = context
    evaluated = datetime.now(timezone.utc).replace(microsecond=0)
    exam_date = (evaluated + timedelta(days=3)).date().isoformat()
    payload = {
        "exam_date": exam_date, "daily_minutes": 30, "timezone": "UTC",
        "evaluated_at": evaluated.isoformat().replace("+00:00", "Z"),
    }
    first = client.post("/api/learning/generate-plan", headers=headers, json=payload)
    assert first.status_code == 200
    plan = first.json()["plan"]
    assert plan["version"] == 1
    assert plan["exam_date"] == exam_date
    assert plan["daily_minutes"] == 30
    assert all(day["estimated_minutes"] <= 30 and day["date"] < exam_date
               for day in plan["plan_data"]["days"])

    payload["daily_minutes"] = 45
    second = client.post("/api/learning/generate-plan", headers=headers, json=payload)
    assert second.json()["plan"]["version"] == 2
    history = client.get("/api/learning/plans", headers=headers).json()["plans"]
    assert [item["status"] for item in history] == ["active", "superseded"]


def test_invalid_plan_does_not_replace_current(context):
    client, _, _, headers = context
    today = datetime.now(timezone.utc).date()
    valid = {"exam_date": (today + timedelta(days=2)).isoformat(), "daily_minutes": 20,
             "timezone": "UTC"}
    assert client.post("/api/learning/generate-plan", headers=headers, json=valid).status_code == 200
    invalid = {**valid, "daily_minutes": 9}
    assert client.post("/api/learning/generate-plan", headers=headers, json=invalid).status_code == 422
    assert client.get("/api/learning/plan", headers=headers).json()["plan"]["version"] == 1


def test_past_exam_is_rejected_and_today_is_returned_as_expired(context):
    client, _, _, headers = context
    today = datetime.now(timezone.utc).date()
    past = {"exam_date": (today - timedelta(days=1)).isoformat(), "daily_minutes": 20,
            "timezone": "UTC"}
    assert client.post("/api/learning/generate-plan", headers=headers, json=past).status_code == 400
    current = {"exam_date": today.isoformat(), "daily_minutes": 20, "timezone": "UTC"}
    response = client.post("/api/learning/generate-plan", headers=headers, json=current)
    assert response.status_code == 200
    assert response.json()["plan"]["status"] == "expired"
    assert response.json()["plan"]["plan_data"]["days"] == []


def test_rule_summary_cites_messages_and_does_not_promote_tutor_claims(context):
    client, db, user_id, headers = context
    conversation_id = db.save_conversation(user_id, 1, "tutor", [
        {"role": "user", "content": "我认为递归和栈有关，但调用帧是什么？"},
        {"role": "assistant", "content": "你已经完全掌握栈。调用帧会保存在栈中。"},
    ])
    response = client.post(
        f"/api/learning/conversations/{conversation_id}/summary", headers=headers,
    )
    assert response.status_code == 200
    summary = response.json()["summary"]["summary_final"]
    assert summary["generation_method"] == "rule"
    assert summary["student_understanding"][0]["message_id"]
    assert not any("完全掌握" in item["text"] for item in summary["student_understanding"])
    assert summary["unresolved_questions"][0]["message_id"]


def test_wrong_answer_creates_editable_owner_scoped_note(context):
    client, _, _, headers = context
    answer = client.post("/api/answer", headers=headers, json={
        "question_id": 1, "answer": "A", "attempt_token": "note-event-1",
    }).json()
    notes = client.get("/api/learning/notes?source_type=answer", headers=headers).json()["notes"]
    assert len(notes) == 1
    note = notes[0]
    assert note["source_id"] == answer["learning_event_id"]
    assert note["auto_content"]["error_reason"]["source"] == "rule"

    updated = client.patch(f"/api/learning/notes/{note['id']}", headers=headers, json={
        "user_content": "我容易把先进先出和后进先出混淆。", "is_pinned": True,
    }).json()["note"]
    assert updated["user_content"].startswith("我容易")
    assert updated["auto_content"] == note["auto_content"]
    archived = client.patch(f"/api/learning/notes/{note['id']}", headers=headers,
                            json={"is_archived": True}).json()["note"]
    assert archived["is_archived"] is True
    assert client.get("/api/learning/notes", headers=headers).json()["notes"] == []
    assert len(client.get("/api/learning/notes?archived=true", headers=headers).json()["notes"]) == 1
