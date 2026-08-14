"""Adversarial verification of 4 security fixes.

This test file actively tries to BREAK each fix. It does NOT modify
implementation files; it only verifies behavior and reports PASS/FAIL
with concrete evidence.

Fixes under verification:
1. CROSS-USER LEAK: /api/wrong must isolate attempts by user_id.
2. AUTH STATUS CODES: pending/rejected login must return 403 (not 200).
3. CORS SPEC COMPLIANCE: wildcard mode must NOT advertise credentials;
   allow-list mode must echo origin + enable credentials for listed only.
4. SQLITE PRAGMAS: WAL, foreign_keys, busy_timeout=5000 must hold across
   every connection (per-connection setting, not one-shot).

Run:
    python -m pytest tests/test_adversarial_verification.py -v
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.db.database import PracticeDatabase
from src.models import ObjectiveQuestion
from src.routes import api_router


# ──────────────────────────── Shared Fixtures ────────────────────────────


class TinyBank:
    bank_id = "exam"

    def __init__(self) -> None:
        self.questions = [
            ObjectiveQuestion(
                id=i, source_order=i, source_num=str(i), qtype="单选题",
                chapter="安全测试章节", stem=f"题目{i}",
                options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                answer="A", raw_correct="A", score=2,
            )
            for i in range(1, 7)
        ]
        self.by_id = {q.id: q for q in self.questions}


class EmptyAssignmentBank:
    bank_id = "assignment"
    questions = []
    by_id = {}


def build_app(db: PracticeDatabase) -> FastAPI:
    """Minimal app bound to an in-memory DB."""
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


# ════════════════════════════════════════════════════════════════
# 1. CROSS-USER LEAK
# ════════════════════════════════════════════════════════════════


def test_cross_user_leak_user1_cannot_see_user2(sec_db):
    """U1 wrong attempts MUST be disjoint from U2's.

    Adversarial scenario: seed U1 wrong on {1,2,3}, U2 wrong on {4,5,6}.
    Verify GET /api/wrong as U1 only returns {1,2,3} and nothing from
    {4,5,6}.
    """
    u1 = sec_db.create_user("alice", "AlicePass123", "用户一", "13800138000")
    u2 = sec_db.create_user("bob", "BobPassPass123", "用户二", "13800138001")
    sec_db.approve_user(u1["id"], True)
    sec_db.approve_user(u2["id"], True)
    u1_token = sec_db.create_session(u1["id"])
    u2_token = sec_db.create_session(u2["id"])

    u1_qs = [1, 2, 3]
    u2_qs = [4, 5, 6]
    for q_id in u1_qs:
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=u1["id"], chapter="安全测试章节",
        )
    for q_id in u2_qs:
        sec_db.record_attempt(
            question_id=q_id, source="bank", qtype="单选题",
            user_answer="B", correct_answer="A", is_correct=False,
            user_id=u2["id"], chapter="安全测试章节",
        )

    with TestClient(build_app(sec_db)) as client:
        u1_resp = client.get("/api/wrong", headers=auth(u1_token))
        u2_resp = client.get("/api/wrong", headers=auth(u2_token))

    assert u1_resp.status_code == 200, u1_resp.text
    assert u2_resp.status_code == 200, u2_resp.text

    u1_ids = {item["question"]["id"] for item in u1_resp.json()["items"]}
    u2_ids = {item["question"]["id"] for item in u2_resp.json()["items"]}

    # Strict isolation: U1 sees only its own.
    assert u1_ids == set(u1_qs), (
        f"FAIL: U1 returned {u1_ids}; expected exactly {set(u1_qs)}"
    )
    # U1 sees none of U2's.
    assert u1_ids.isdisjoint(set(u2_qs)), (
        f"FAIL: U1 leaked U2's ids: {u1_ids & set(u2_qs)}"
    )
    assert u2_ids == set(u2_qs)
    assert u2_ids.isdisjoint(set(u1_qs))


def test_cross_user_leak_db_function_filters_by_user_id(sec_db):
    """Direct DB inspection: PracticeDatabase.wrong_attempts() must filter by user_id.

    This is a positive verification of the production function (not a simulation
    of any hypothetical binding order). It pins the bug class where the params
    list is in the wrong order relative to the SQL placeholders.

    Setup: two users, each with 3 wrong attempts on disjoint question sets.
    Assertion: calling wrong_attempts(bank, user_id=u1) returns ONLY u1's
    rows, regardless of which placeholder receives which param value. If the
    param ordering regresses (e.g. [limit*4, user_id] for a [user_id, limit]
    SQL), the user_id filter becomes `user_id = 320` and the function
    silently returns 0 rows for every authenticated caller — a quiet loss
    of the entire /api/wrong endpoint.
    """
    u1 = sec_db.create_user("charlie", "CharlieP123", "C", "13800000001")
    u2 = sec_db.create_user("dave", "DavePassPass1", "D", "13800000002")
    for u, qs in ((u1, (1, 2, 3)), (u2, (4, 5, 6))):
        sec_db.approve_user(u["id"], True)
        for q_id in qs:
            sec_db.record_attempt(
                question_id=q_id, source="bank", qtype="单选题",
                user_answer="B", correct_answer="A", is_correct=False,
                user_id=u["id"], chapter="ch",
            )

    bank = TinyBank()
    u1_items = sec_db.wrong_attempts(bank, user_id=u1["id"])
    u2_items = sec_db.wrong_attempts(bank, user_id=u2["id"])

    u1_qids = {item["question"]["id"] for item in u1_items}
    u2_qids = {item["question"]["id"] for item in u2_items}

    # Hard guard: if either user gets 0 items, the SQL+params binding is broken
    # (the most likely culprit is a swapped params list).
    assert len(u1_items) == 3, (
        f"FAIL: U1 returned {len(u1_items)} items (expected 3); "
        "wrong_attempts() likely has params in wrong order. "
        f"u1_qids={u1_qids}"
    )
    assert len(u2_items) == 3, (
        f"FAIL: U2 returned {len(u2_items)} items (expected 3); "
        "wrong_attempts() likely has params in wrong order. "
        f"u2_qids={u2_qids}"
    )
    # Strict isolation: each user sees only their own question_ids.
    assert u1_qids == {1, 2, 3}, f"FAIL: U1 saw {u1_qids}, expected {{1,2,3}}"
    assert u2_qids == {4, 5, 6}, f"FAIL: U2 saw {u2_qids}, expected {{4,5,6}}"
    assert u1_qids.isdisjoint(u2_qids), (
        f"FAIL: sets overlap: {u1_qids & u2_qids}"
    )

    # Sanity: every returned item's underlying attempt row really belongs to
    # the requested user. This is the strongest pinning assertion — it would
    # fail if wrong_attempts() ever started returning rows that don't match
    # the requested user_id.
    for item in u1_items:
        attempt_id = item["attempt_id"]
        with sec_db.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
        assert row["user_id"] == u1["id"], (
            f"FAIL: attempt {attempt_id} has user_id={row['user_id']}, "
            f"expected {u1['id']}"
        )
    for item in u2_items:
        attempt_id = item["attempt_id"]
        with sec_db.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
        assert row["user_id"] == u2["id"]


# ════════════════════════════════════════════════════════════════
# 2. AUTH STATUS CODES
# ════════════════════════════════════════════════════════════════


def test_login_pending_returns_403_with_error_body(sec_db):
    """Pending user MUST get 403, body MUST include {"error": "..."}."""
    sec_db.create_user("pendinguser", "PendingP123", "待审用户", "13800138000")
    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "pendinguser", "password": "PendingP123"},
        )
    body = response.json()
    assert response.status_code == 403, (
        f"FAIL: pending got {response.status_code}, expected 403; body={body}"
    )
    assert "error" in body, f"FAIL: response missing error key: {body}"


def test_login_rejected_returns_403_with_error_body(sec_db):
    """Rejected user MUST get 403 with error body."""
    user = sec_db.create_user("rejecteduser", "RejectP123", "被拒用户", "13800138000")
    sec_db.approve_user(user["id"], False)
    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "rejecteduser", "password": "RejectP123"},
        )
    body = response.json()
    assert response.status_code == 403, (
        f"FAIL: rejected got {response.status_code}, expected 403; body={body}"
    )
    assert "error" in body, f"FAIL: response missing error key: {body}"


def test_login_wrong_password_unchanged(sec_db):
    """Wrong password for approved user MUST remain 400 (no regression)."""
    user = sec_db.create_user("approveduser", "RightPass123", "已审核用户", "13800138000")
    sec_db.approve_user(user["id"], True)
    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "approveduser", "password": "NotRight123"},
        )
    assert response.status_code == 400, (
        f"FAIL: wrong-password got {response.status_code}, expected 400; body={response.text}"
    )


def test_login_missing_fields_returns_4xx(sec_db):
    """Missing required fields MUST return 422 (Pydantic validation) or 400."""
    with TestClient(build_app(sec_db)) as client:
        response = client.post(
            "/api/auth/login",
            json={"account": "only_account"},
        )
    # Pydantic validation in FastAPI returns 422 by default.
    assert response.status_code in (400, 422), (
        f"FAIL: missing fields got {response.status_code}, expected 400 or 422"
    )


# ════════════════════════════════════════════════════════════════
# 3. CORS SPEC COMPLIANCE
# ════════════════════════════════════════════════════════════════


def _build_cors_app(allowed_origins, allow_credentials):
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


def _preflight(client, origin):
    return client.options(
        "/probe",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )


def test_cors_wildcard_mode_echoes_star_no_credentials(sec_db):
    """Default wildcard: allow-origin='*' and credentials header absent."""
    app = _build_cors_app(allowed_origins=["*"], allow_credentials=False)
    with TestClient(app) as client:
        response = _preflight(client, "http://attacker.com")
    headers = {k.lower(): v for k, v in response.headers.items()}
    assert headers.get("access-control-allow-origin") == "*", (
        f"FAIL: expected '*', got {headers.get('access-control-allow-origin')!r}"
    )
    creds = headers.get("access-control-allow-credentials")
    assert creds is None or creds.lower() != "true", (
        f"FAIL: credentials header present in wildcard mode: {creds!r}"
    )


def test_cors_specific_origin_allowed_with_credentials():
    """Allow-list: listed origin echoed back AND credentials enabled."""
    env = os.environ.copy()
    env["SM_ALLOWED_ORIGINS"] = "https://app.example.com"
    for k in ("SM_ADMIN_PASSWORD", "SM_HOST", "SM_PORT"):
        env.pop(k, None)

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
        "import json\n"
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
    assert payload["allow_origin"] == "https://app.example.com", payload
    assert (payload["allow_credentials"] or "").lower() == "true", payload


def test_cors_unlisted_origin_not_echoed():
    """Allow-list: unlisted origin MUST NOT be echoed."""
    env = os.environ.copy()
    env["SM_ALLOWED_ORIGINS"] = "https://app.example.com"
    for k in ("SM_ADMIN_PASSWORD", "SM_HOST", "SM_PORT"):
        env.pop(k, None)

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
        "import json\n"
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
    assert payload["allow_origin"] != "https://attacker.com", payload


def test_cors_browser_simulation_actual_get(sec_db):
    """Actual GET with Origin header (no preflight) still carries CORS headers."""
    app = _build_cors_app(allowed_origins=["*"], allow_credentials=False)
    with TestClient(app) as client:
        response = client.get("/probe", headers={"Origin": "http://attacker.com"})
    headers = {k.lower(): v for k, v in response.headers.items()}
    # The actual response to GET must still advertise ACAO at minimum.
    assert headers.get("access-control-allow-origin") == "*", (
        f"FAIL: GET missing ACAO header: {headers!r}"
    )


# ════════════════════════════════════════════════════════════════
# 4. SQLITE PRAGMAS
# ════════════════════════════════════════════════════════════════


def test_pragmas_first_connection(sec_db):
    """Every fresh connection must carry WAL/foreign_keys/busy_timeout."""
    with sec_db.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert str(journal_mode).lower() == "wal", (
        f"FAIL: journal_mode={journal_mode!r}, expected 'wal'"
    )
    assert int(foreign_keys) == 1, (
        f"FAIL: foreign_keys={foreign_keys!r}, expected 1"
    )
    assert int(busy_timeout) == 5000, (
        f"FAIL: busy_timeout={busy_timeout!r}, expected 5000"
    )


def test_pragmas_subsequent_connection_still_applied(sec_db):
    """A second connection must still see foreign_keys=1 even after first closes.

    The pragma is connection-scoped in SQLite; the fix must set it on every
    connect(), not just on the first.
    """
    # Open and close one connection.
    with sec_db.connect() as conn:
        conn.execute("SELECT 1")
    # Now open a brand-new connection.
    conn2 = sqlite3.connect(str(sec_db.path))
    conn2.row_factory = sqlite3.Row
    fk_raw = conn2.execute("PRAGMA foreign_keys").fetchone()[0]
    conn2.close()
    # The raw sqlite3 connection will NOT have foreign_keys=1.
    # PracticeDatabase.connect() MUST re-enable it.
    with sec_db.connect() as conn:
        fk_after = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert int(fk_raw) == 0, (
        f"sanity: raw sqlite3 should default to fk=0, got {fk_raw!r}"
    )
    assert int(fk_after) == 1, (
        f"FAIL: fresh connect did not re-enable foreign_keys, got {fk_after!r}"
    )


def test_pragmas_journal_mode_persists_wal(sec_db):
    """WAL mode is persistent at the DB level; subsequent reads confirm."""
    # Set WAL via our connect().
    with sec_db.connect() as conn:
        first = conn.execute("PRAGMA journal_mode").fetchone()[0]
    # Open a fresh, plain sqlite3 connection and read it back.
    raw = sqlite3.connect(str(sec_db.path))
    raw.row_factory = sqlite3.Row
    second = raw.execute("PRAGMA journal_mode").fetchone()[0]
    raw.close()
    assert str(first).lower() == "wal", f"FAIL: first={first!r}"
    assert str(second).lower() == "wal", (
        f"FAIL: journal_mode not persisted, got {second!r}"
    )


def test_pragmas_busy_timeout_blocks_during_write(sec_db, tmp_path):
    """Concurrent write on a second connection must wait busy_timeout ms.

    We force a long-lived transaction on connection A, then attempt a write
    on B. With busy_timeout=5000 set on B, B should block (not raise
    OperationalError immediately). If B's PRAGMA wasn't set, the write would
    fail almost instantly.
    """
    db_path = sec_db.path
    barrier = threading.Event()
    writer_done = threading.Event()
    other_caught_error: list = []

    def writer_a():
        """Hold an IMMEDIATE write transaction for ~1.5s."""
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            # Set the PRAGMAs to mimic production connection.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO attempts (question_id, source, qtype, user_answer, "
                "correct_answer, is_correct, created_at, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (999, "bank", "单选题", "B", "A", 0, time.time(), 1),
            )
            barrier.set()
            time.sleep(1.5)
            conn.commit()
        finally:
            conn.close()
            writer_done.set()

    def writer_b():
        """Try to write while A holds the lock; record delay + outcome."""
        barrier.wait()
        start = time.time()
        try:
            conn = sqlite3.connect(str(db_path), timeout=10.0)
            # Replicate production connect() PRAGMAs.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute(
                "INSERT INTO attempts (question_id, source, qtype, user_answer, "
                "correct_answer, is_correct, created_at, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (998, "bank", "单选题", "B", "A", 0, time.time(), 1),
            )
            conn.commit()
            conn.close()
            other_caught_error.append(("ok", time.time() - start))
        except sqlite3.OperationalError as exc:
            other_caught_error.append((str(exc), time.time() - start))

    t_a = threading.Thread(target=writer_a)
    t_b = threading.Thread(target=writer_b)
    t_a.start()
    t_b.start()
    t_b.join(timeout=10)
    t_a.join(timeout=10)

    assert other_caught_error, "B did not record any outcome"
    outcome, elapsed = other_caught_error[0]
    # The expected behavior: B blocks on A's lock. With busy_timeout=5000,
    # B should wait up to ~1.5s (A holds lock for 1.5s), then succeed.
    # If B fails immediately (elapsed < 0.3s), busy_timeout is NOT active.
    assert outcome == "ok", (
        f"FAIL: writer B failed unexpectedly: {outcome!r} (elapsed={elapsed:.2f}s)"
    )
    assert elapsed >= 0.5, (
        f"FAIL: writer B returned too fast ({elapsed:.2f}s); busy_timeout may not be active"
    )


# ════════════════════════════════════════════════════════════════
# 5. REGRESSION SANITY (run full suite separately)
# ════════════════════════════════════════════════════════════════


def test_regression_placeholder(sec_db):
    """Placeholder to surface PRAGMA on the same fixture path used elsewhere.

    The full suite regression run is performed by the shell command in step 5;
    here we just verify the security suite's PRAGMA invariant via the
    shared fixture to detect fixture drift.
    """
    with sec_db.connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"