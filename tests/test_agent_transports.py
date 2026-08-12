from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.agents.orchestrator import ModelStreamEvent
from src.db.database import PracticeDatabase
from src.routes import api_router


class EmptyBank:
    by_id = {}
    questions = []
    discussion_by_id = {}


class StreamingGateway:
    calls = 0

    async def stream(self, **_kwargs):
        type(self).calls += 1
        yield ModelStreamEvent(type="delta", content="第一")
        yield ModelStreamEvent(type="delta", content="片段")
        yield ModelStreamEvent(type="done", finish_reason="stop")


def make_app(tmp_path):
    db = PracticeDatabase(tmp_path / "transport.sqlite3")
    user = db.create_user("agentuser", "StudentPass123", "Agent", "13800138000")
    db.approve_user(user["id"], True)
    token = db.create_session(user["id"])
    app = FastAPI()
    app.state.db = db
    app.state.exam_bank = EmptyBank()
    app.state.assignment_bank = EmptyBank()
    app.state.agent_gateway_factory = lambda _model=None: StreamingGateway()
    app.state._json_response = lambda body, status=200: JSONResponse(body, status_code=status)

    @app.exception_handler(PermissionError)
    async def permission_error_handler(_request, exc):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    app.include_router(api_router)
    return app, token


def event_signature(events):
    return [
        (event["protocol"], event["type"], event.get("content"))
        for event in events
    ]


def test_rest_and_sse_share_the_same_event_protocol(tmp_path):
    app, token = make_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        rest = client.post("/api/ai/tutor", json={"message": "什么是栈"}, headers=headers)
        streamed = client.post("/api/ai/tutor/stream", json={"message": "什么是栈"}, headers=headers)

    assert rest.status_code == 200
    assert streamed.status_code == 200
    rest_events = rest.json()["events"]
    sse_events = [
        json.loads(line[6:])
        for line in streamed.text.splitlines()
        if line.startswith("data: ")
    ]
    assert event_signature(rest_events) == event_signature(sse_events)
    assert [event["type"] for event in sse_events] == [
        "meta", "route", "delta", "delta", "done",
    ]
    assert rest.json()["reply"] == "第一片段"
    assert sse_events[-1]["conversation_id"]


def test_multi_agent_route_is_the_same_streaming_core(tmp_path):
    app, token = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/ai/multi-agent/tutor",
            json={"message": "帮我理解二叉树"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["mode"] == "multi_agent"
    assert [item["type"] for item in response.json()["events"]][-3:] == [
        "delta", "delta", "done",
    ]


def test_internal_agent_requires_service_key_before_gateway(tmp_path, monkeypatch):
    app, _token = make_app(tmp_path)
    monkeypatch.setattr("src.routes.deps.AGENT_SERVICE_KEY", "service-secret")
    StreamingGateway.calls = 0
    payload = {"external_user_id": "cloud-user", "message": "解释队列"}

    with TestClient(app) as client:
        missing = client.post("/api/internal/agent/tutor", json=payload)
        wrong = client.post(
            "/api/internal/agent/tutor",
            json=payload,
            headers={"X-StructMind-Service-Key": "wrong"},
        )
        accepted = client.post(
            "/api/internal/agent/tutor",
            json=payload,
            headers={"X-StructMind-Service-Key": "service-secret"},
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert StreamingGateway.calls == 1
    assert accepted.status_code == 200
    assert accepted.json()["protocol"] == "structmind.agent.v1"
    assert accepted.json()["reply"] == "第一片段"
    assert all("conversation_id" not in event for event in accepted.json()["events"])


def test_web_and_unicloud_service_surface_return_identical_protocol_signatures(tmp_path, monkeypatch):
    app, token = make_app(tmp_path)
    monkeypatch.setattr("src.routes.deps.AGENT_SERVICE_KEY", "service-secret")
    with TestClient(app) as client:
        web = client.post(
            "/api/ai/multi-agent/tutor/stream",
            json={"message": "解释图", "mode": "multi-agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        service = client.post(
            "/api/internal/agent/tutor",
            json={
                "external_user_id": "cloud-user",
                "message": "解释图",
                "mode": "multi_agent",
            },
            headers={"X-StructMind-Service-Key": "service-secret"},
        )

    web_events = [
        json.loads(line[6:])
        for line in web.text.splitlines()
        if line.startswith("data: ")
    ]
    assert web.status_code == 200
    assert service.status_code == 200
    assert event_signature(web_events) == event_signature(service.json()["events"])
    assert [item["content"] for item in web_events if item["type"] == "delta"] == [
        "第一", "片段",
    ]
