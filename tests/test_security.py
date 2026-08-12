"""阶段 0 安全边界与 AI 额度测试。"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.db.database import PracticeDatabase
from src.config import ADMIN_ACCOUNT
from src.routes import api_router


class EmptyBank:
    by_id = {}
    discussion_by_id = {}


def build_app(db: PracticeDatabase) -> FastAPI:
    app = FastAPI()
    app.state.db = db
    app.state.exam_bank = EmptyBank()
    app.state.assignment_bank = EmptyBank()
    app.state._json_response = lambda body, status=200: JSONResponse(
        body, status_code=status,
    )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(_request, exc):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    app.include_router(api_router)
    return app


@pytest.fixture
def security_db(tmp_path: Path) -> PracticeDatabase:
    return PracticeDatabase(tmp_path / "security.sqlite3")


def create_approved_user(db: PracticeDatabase, account: str, *, admin: bool = False):
    user = db.create_user(account, "StudentPass123", account, "13800138000")
    db.approve_user(user["id"], True)
    if admin:
        with db.connect() as conn:
            conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
    token = db.create_session(user["id"])
    return user, token


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/admin/pending", None),
        ("get", "/api/admin/users", None),
        ("post", "/api/admin/approve", {"user_id": 1, "approved": True}),
        ("post", "/api/config", {"default_model": "glm-5.1"}),
    ],
)
def test_admin_mutations_reject_anonymous_users(
    security_db, method, path, payload,
):
    with TestClient(build_app(security_db)) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/admin/pending", None),
        ("get", "/api/admin/users", None),
        ("post", "/api/admin/approve", {"user_id": 999, "approved": True}),
        ("post", "/api/config", {"default_model": "glm-5.1"}),
    ],
)
def test_admin_mutations_reject_students(
    security_db, method, path, payload,
):
    _user, token = create_approved_user(security_db, "student")
    with TestClient(build_app(security_db)) as client:
        response = client.request(
            method,
            path,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


def test_admin_can_read_pending_users(security_db):
    _admin, token = create_approved_user(security_db, "adminuser", admin=True)
    with TestClient(build_app(security_db)) as client:
        response = client.get(
            "/api/admin/pending",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"users": []}


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/ai/generate", {"qtype": "单选题"}),
        ("/api/ai/answer", {"ai_question_id": "missing", "answer": "A"}),
        ("/api/ai/supplement", {"question_id": 1}),
        ("/api/ai/tutor", {"message": "什么是栈"}),
        ("/api/ai/tutor/stream", {"message": "什么是栈"}),
        ("/api/ai/multi-agent/tutor", {"message": "什么是栈"}),
        ("/api/ai/multi-agent/tutor/stream", {"message": "什么是栈"}),
        ("/api/question/ai", {"question_id": 1}),
        ("/api/question/ai/stream", {"question_id": 1}),
        ("/api/assignment/grade", {"question_id": 1, "answer": "测试回答"}),
        ("/api/discussion/grade", {"discussion_id": 1, "answer": "测试回答"}),
    ],
)
def test_anonymous_ai_requests_are_rejected_before_provider_use(
    security_db, monkeypatch, path, payload,
):
    def provider_must_not_start(*_args, **_kwargs):
        raise AssertionError("匿名请求不应创建 AI 客户端")

    monkeypatch.setattr("src.routes.ai._get_ai_client", provider_must_not_start)
    monkeypatch.setattr("src.routes.ai.AsyncModelGateway", provider_must_not_start)
    monkeypatch.setattr("src.routes.assignment.AIClient", provider_must_not_start)

    with TestClient(build_app(security_db)) as client:
        response = client.post(path, json=payload)

    assert response.status_code == 403


def test_ai_request_quota_is_enforced_per_user(security_db, monkeypatch):
    _user, token = create_approved_user(security_db, "limiteduser")

    from src.agents.orchestrator import ModelStreamEvent

    class FakeGateway:
        async def stream(self, **_kwargs):
            yield ModelStreamEvent(type="delta", content="请先说说你对栈的理解。")
            yield ModelStreamEvent(type="done", finish_reason="stop")

    app = build_app(security_db)
    app.state.agent_gateway_factory = lambda _model=None: FakeGateway()
    app.state.ai_rate_limit_max = 1
    app.state.ai_rate_limit_window = 60

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post("/api/ai/tutor", json={"message": "什么是栈"}, headers=headers)
        second = client.post("/api/ai/tutor", json={"message": "什么是队列"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429


def test_application_has_no_builtin_admin_password():
    env = os.environ.copy()
    env.pop("SM_ADMIN_PASSWORD", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.config import ADMIN_PASSWORD; "
            "raise SystemExit(0 if ADMIN_PASSWORD is None else 1)",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def test_admin_bootstrap_is_skipped_without_explicit_password(monkeypatch):
    import server

    class FakeDatabase:
        def __init__(self):
            self.calls = []

        def ensure_admin(self, *args):
            self.calls.append(args)

    db = FakeDatabase()
    monkeypatch.setattr(server, "ADMIN_PASSWORD", None)

    created = server.bootstrap_admin(db)

    assert created is False
    assert db.calls == []


def test_public_registration_cannot_claim_reserved_admin_account(security_db):
    with TestClient(build_app(security_db)) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "account": ADMIN_ACCOUNT,
                "password": "AttackerPass123",
                "name": "攻击者",
                "phone": "13800138000",
            },
        )

    assert response.status_code == 403
    assert security_db.authenticate(ADMIN_ACCOUNT, "AttackerPass123") is None


def test_normal_user_creation_never_infers_admin_role_from_account_name(security_db):
    user = security_db.create_user(
        ADMIN_ACCOUNT,
        "StudentPass123",
        "保留账号",
        "13800138000",
    )

    assert user["role"] == "student"
    assert user["status"] == "pending"
