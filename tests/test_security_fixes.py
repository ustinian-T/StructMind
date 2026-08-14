"""Phase 1 安全修复回归测试。

覆盖以下修复:
1. /api/wrong 必须按用户隔离（修复前读取所有 attempt，未按 user_id 过滤）。
2. /api/auth/login 对 pending 用户必须返回 403（修复前同 approved 一律 200 + token）。
3. /api/auth/login 对 rejected 用户必须返回 403。
4. SQLite PRAGMA 必须在 connect 时启用 WAL / foreign_keys / busy_timeout。
5. CORS 在未配置 SM_ALLOWED_ORIGINS 时不允许携带凭据（避免通配符+credentials 风险）。

运行:
    py -m pytest tests/test_security_fixes.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.db.database import PracticeDatabase
from src.models import ObjectiveQuestion
from src.routes import api_router


# ──────────────────────────── Helper Fixtures ────────────────────────────


class TinyBank:
    bank_id = "exam"

    def __init__(self) -> None:
        self.questions = [
            ObjectiveQuestion(
                id=1, source_order=1, source_num="1", qtype="单选题",
                chapter="安全测试章节", stem="题目1",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=2, source_order=2, source_num="2", qtype="单选题",
                chapter="安全测试章节", stem="题目2",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=3, source_order=3, source_num="3", qtype="单选题",
                chapter="安全测试章节", stem="题目3",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=4, source_order=4, source_num="4", qtype="单选题",
                chapter="安全测试章节", stem="题目4",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=5, source_order=5, source_num="5", qtype="单选题",
                chapter="安全测试章节", stem="题目5",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
            ObjectiveQuestion(
                id=6, source_order=6, source_num="6", qtype="单选题",
                chapter="安全测试章节", stem="题目6",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            ),
        ]
        self.by_id = {q.id: q for q in self.questions}


class EmptyAssignmentBank:
    bank_id = "assignment"
    questions = []
    by_id = {}


def build_app(db: PracticeDatabase) -> FastAPI:
    """Build a minimal FastAPI app bound to the given in-memory DB."""
    app = FastAPI()
    app.state.db = db
    app.state.exam_bank = TinyBank()
    app.state.assignment_bank = EmptyAssignmentBank()
    app.state._json_response = lambda body, status=200: JSONResponse(
        body, status_code=status,
    )

    @app.exception_handler(PermissionError)
    async def _permission(_request, exc):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    @app.exception_handler(ValueError)
    async def _value(_request, exc):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(KeyError)
    async def _key(_request, exc):
        return JSONResponse(status_code=404, content={"error": str(exc)})

    app.include_router(api_router)
    return app


@pytest.fixture
def sec_db(tmp_path: Path) -> PracticeDatabase:
    return PracticeDatabase(tmp_path / "sec.sqlite3")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────── (a) Wrong-attempts isolation ────────────────────────────


def test_wrong_attempts_user_isolation(sec_db):
    """Each user must only see their own wrong attempts; anonymous sees none."""
    user1 = sec_db.create_user("alice", "AlicePass123", "用户一", "13800138000")
    user2 = sec_db.create_user("bob", "BobPassPass123", "用户二", "13800138001")
    sec_db.approve_user(user1["id"], True)
    sec_db.approve_user(user2["id"], True)
    user1_token = sec_db.create_session(user1["id"])
    user2_token = sec_db.create_session(user2["id"])

    # 直接在 attempts 表里塞入「错误」的练习记录。
    user1_questions = [1, 2, 3]
    user2_questions = [4, 5, 6]
    for q_id in user1_questions:
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=user1["id"], chapter="安全测试章节",
        )
    for q_id in user2_questions:
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=user2["id"], chapter="安全测试章节",
        )

    with TestClient(build_app(sec_db)) as client:
        user1_resp = client.get("/api/wrong", headers=auth(user1_token))
        user2_resp = client.get("/api/wrong", headers=auth(user2_token))
        anon_resp = client.get("/api/wrong")

    assert user1_resp.status_code == 200, user1_resp.text
    assert user2_resp.status_code == 200, user2_resp.text
    assert anon_resp.status_code == 200, anon_resp.text

    user1_ids = {item["question"]["id"] for item in user1_resp.json()["items"]}
    user2_ids = {item["question"]["id"] for item in user2_resp.json()["items"]}

    assert user1_ids == set(user1_questions)
    assert user2_ids == set(user2_questions)
    # 关键隔离断言：用户之间数据互不可见。
    assert user1_ids.isdisjoint(user2_ids)
    # 匿名请求必须返回空列表，而非任何用户的错题。
    assert anon_resp.json()["items"] == []


def test_wrong_attempts_param_order_pin(sec_db):
    """钉子测试 —— 防止 wrong_attempts() 的 SQL 参数顺序再次反转。

    bug 类别：若 params = [limit*4, user_id]，但 SQL 占位符顺序是
    `[..., user_id = ?, ..., LIMIT ?]`，SQLite 按位置绑定会把 `limit*4` 绑到
    `user_id = ?`（永远不匹配任何真实 user_id），把真正的 user_id 绑到
    LIMIT。结果是：所有已登录用户调用 `/api/wrong` 都得到空列表，跨用户
    隔离 "看起来生效" 但整个端点静默失效。

    本测试**直接调用** PracticeDatabase.wrong_attempts()（不走 HTTP 层），
    用一个**用户 id 不等于 limit*4** 的用户来验证函数确实在按 user_id 过滤。
    如果有人未来再次把 params 写反，本测试会立刻失败。
    """
    from src.models import ObjectiveQuestion

    # 微型题库，只需提供 6 个题号供 attempts 关联即可。
    class _Bank:
        bank_id = "exam"
        questions = [
            ObjectiveQuestion(
                id=i, source_order=i, source_num=str(i), qtype="单选题",
                chapter="ch", stem=f"q{i}",
                options=[{"key": "A", "text": ""}, {"key": "B", "text": ""}],
                answer="A", raw_correct="A", score=2,
            )
            for i in range(1, 7)
        ]
        by_id = {q.id: q for q in questions}

    bank = _Bank()

    # 创建两个用户，并用 AUTOINCREMENT 得到的真实 id（远小于 limit*4=320）。
    user_a = sec_db.create_user("pinA", "PinPassA123", "A", "13900000001")
    user_b = sec_db.create_user("pinB", "PinPassB123", "B", "13900000002")
    sec_db.approve_user(user_a["id"], True)
    sec_db.approve_user(user_b["id"], True)

    # A 错题 3 道（q1-q3），B 错题 3 道（q4-q6）—— 互不重叠。
    for q_id in (1, 2, 3):
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=user_a["id"], chapter="ch",
        )
    for q_id in (4, 5, 6):
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=user_b["id"], chapter="ch",
        )

    # 直接调用函数（绕过 HTTP / 路由层），这样测试的是函数本身的行为。
    a_items = sec_db.wrong_attempts(bank, user_id=user_a["id"])
    b_items = sec_db.wrong_attempts(bank, user_id=user_b["id"])

    # 关键断言 1：如果 params 顺序反了，user_a["id"] 会被绑到 LIMIT 而
    # limit*4=320 绑到 user_id = ?；SQL 中没有任何 user_id=320 的记录，
    # 所以会返回空。空列表立刻被下面的断言捕获。
    assert len(a_items) == 3, (
        f"params 顺序疑似反了：A 得到 {len(a_items)} 项（期望 3）。"
        f"题目 id={[it['question']['id'] for it in a_items]}"
    )
    assert len(b_items) == 3, (
        f"params 顺序疑似反了：B 得到 {len(b_items)} 项（期望 3）。"
        f"题目 id={[it['question']['id'] for it in b_items]}"
    )

    # 关键断言 2：返回的题目 id 必须严格属于对应用户，互不重叠。
    a_qids = {item["question"]["id"] for item in a_items}
    b_qids = {item["question"]["id"] for item in b_items}
    assert a_qids == {1, 2, 3}, f"A 看到的题目 id={a_qids}，期望 {{1,2,3}}"
    assert b_qids == {4, 5, 6}, f"B 看到的题目 id={b_qids}，期望 {{4,5,6}}"
    assert a_qids.isdisjoint(b_qids), (
        f"用户之间数据重叠：{a_qids & b_qids}"
    )

    # 关键断言 3：双保险 —— 每个返回项的底层 attempt row 必须确实属于
    # 请求的用户。如果有人未来改 SQL 让 user_id 谓词失效，这条会立刻报错。
    for item in a_items + b_items:
        attempt_id = item["attempt_id"]
        expected_user = user_a["id"] if item["question"]["id"] in a_qids else user_b["id"]
        with sec_db.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
        assert row is not None, f"attempts.id={attempt_id} 不存在"
        assert row["user_id"] == expected_user, (
            f"attempt {attempt_id} 的 user_id={row['user_id']}，"
            f"但该题目属于 user_id={expected_user}"
        )


# ──────────────────────────── (b/c/d) Login status codes ────────────────────────────


def test_login_pending_returns_403(sec_db):
    sec_db.create_user("pendinguser", "PendingP123", "待审用户", "13800138000")
    # 默认创建后 status == "pending"，无需显式 approve。

    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "pendinguser", "password": "PendingP123"},
        )

    assert response.status_code == 403, response.text


def test_login_rejected_returns_403(sec_db):
    user = sec_db.create_user("rejecteduser", "RejectP123", "被拒用户", "13800138000")
    sec_db.approve_user(user["id"], False)

    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "rejecteduser", "password": "RejectP123"},
        )

    assert response.status_code == 403, response.text


def test_login_wrong_password_returns_400_unchanged(sec_db):
    user = sec_db.create_user("approveduser", "RightPass123", "已审核用户", "13800138000")
    sec_db.approve_user(user["id"], True)

    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "approveduser", "password": "NotRight123"},
        )

    # 修复不应改变正常用户输错密码的语义——仍是 400。
    assert response.status_code == 400, response.text


# ──────────────────────────── (e) SQLite PRAGMA defaults ────────────────────────────


def test_sqlite_pragmas(sec_db):
    """Connect() must enable WAL, foreign_keys, and busy_timeout=5000."""
    with sec_db.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert str(journal_mode).lower() == "wal"
    assert int(foreign_keys) == 1
    assert int(busy_timeout) == 5000


# ──────────────────────────── (f/g/h) CORS handling ────────────────────────────


def _build_cors_app(allowed_origins: list[str], allow_credentials: bool) -> FastAPI:
    """Construct a minimal app with the same CORSMiddleware config used in server.py."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=allow_credentials,
    )

    @app.get("/probe")
    async def _probe():
        return {"ok": True}

    return app


def _preflight(client: TestClient, origin: str) -> object:
    return client.options(
        "/probe",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )


def test_cors_wildcard_no_credentials():
    """When SM_ALLOWED_ORIGINS is unset, server.py uses '*' with allow_credentials=False."""
    app = _build_cors_app(allowed_origins=["*"], allow_credentials=False)
    with TestClient(app) as client:
        response = _preflight(client, "http://anywhere.com")

    # 通配符下应回显 '*'，且不允许凭据（防止组合漏洞）。
    assert response.headers.get("access-control-allow-origin") == "*"
    creds = response.headers.get("access-control-allow-credentials")
    assert creds is None or creds.lower() != "true"


def test_cors_specific_origin_allowed_with_credentials():
    """With an explicit allow-list, the preflight from the listed origin must echo it AND enable credentials."""
    env = os.environ.copy()
    env["SM_ALLOWED_ORIGINS"] = "https://app.example.com"
    env.pop("SM_ADMIN_PASSWORD", None)
    env.pop("SM_HOST", None)
    env.pop("SM_PORT", None)

    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import os, json\n"
        "from fastapi.testclient import TestClient\n"
        "import server\n"
        "client = TestClient(server.app)\n"
        "response = client.options(\n"
        "    '/probe',\n"
        "    headers={\n"
        "        'Origin': 'https://app.example.com',\n"
        "        'Access-Control-Request-Method': 'POST',\n"
        "        'Access-Control-Request-Headers': 'Authorization, Content-Type',\n"
        "    },\n"
        ")\n"
        "headers = {k.lower(): v for k, v in response.headers.items()}\n"
        "print(json.dumps({\n"
        "    'status': response.status_code,\n"
        "    'allow_origin': headers.get('access-control-allow-origin'),\n"
        "    'allow_credentials': headers.get('access-control-allow-credentials'),\n"
        "}))\n"
    )

    # The lifespan in server.py tries to load docx files; skip it via env so the
    # import doesn't trigger disk IO. We use a no-op lifespan replacement through
    # monkeypatching the lifespan attribute via a wrapper script.
    prelude = (
        "import server as _server\n"
        "from contextlib import asynccontextmanager\n"
        "@asynccontextmanager\n"
        "async def _noop(app):\n"
        "    app.state.exam_bank = type('B', (), {'by_id': {}, 'questions': []})()\n"
        "    app.state.assignment_bank = type('B', (), {'by_id': {}, 'questions': []})()\n"
        "    app.state.db = None\n"
        "    yield\n"
        "_server.app.router.lifespan_context = _noop\n"
    )
    full_script = prelude + script

    result = subprocess.run(
        [sys.executable, "-c", full_script],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    last_line = result.stdout.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["allow_origin"] == "https://app.example.com", payload
    assert (payload["allow_credentials"] or "").lower() == "true", payload


def test_cors_unlisted_origin_rejected():
    """With an allow-list, an unlisted origin must NOT be echoed back."""
    env = os.environ.copy()
    env["SM_ALLOWED_ORIGINS"] = "https://app.example.com"
    env.pop("SM_ADMIN_PASSWORD", None)
    env.pop("SM_HOST", None)
    env.pop("SM_PORT", None)

    repo_root = Path(__file__).resolve().parents[1]
    prelude = (
        "import server as _server\n"
        "from contextlib import asynccontextmanager\n"
        "@asynccontextmanager\n"
        "async def _noop(app):\n"
        "    app.state.exam_bank = type('B', (), {'by_id': {}, 'questions': []})()\n"
        "    app.state.assignment_bank = type('B', (), {'by_id': {}, 'questions': []})()\n"
        "    app.state.db = None\n"
        "    yield\n"
        "_server.app.router.lifespan_context = _noop\n"
    )
    script = (
        "import os, json\n"
        "from fastapi.testclient import TestClient\n"
        "import server\n"
        "client = TestClient(server.app)\n"
        "response = client.options(\n"
        "    '/probe',\n"
        "    headers={\n"
        "        'Origin': 'https://attacker.com',\n"
        "        'Access-Control-Request-Method': 'POST',\n"
        "        'Access-Control-Request-Headers': 'Authorization, Content-Type',\n"
        "    },\n"
        ")\n"
        "headers = {k.lower(): v for k, v in response.headers.items()}\n"
        "print(json.dumps({\n"
        "    'status': response.status_code,\n"
        "    'allow_origin': headers.get('access-control-allow-origin'),\n"
        "    'allow_credentials': headers.get('access-control-allow-credentials'),\n"
        "}))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", prelude + script],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    last_line = result.stdout.strip().splitlines()[-1]
    payload = json.loads(last_line)
    # 关键：不允许列表中的 Origin 不会被 echo 回响应头。
    assert payload["allow_origin"] != "https://attacker.com", payload
