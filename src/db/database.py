"""PracticeDatabase —— SQLite 练习数据库操作。

完整提取自 server.py PracticeDatabase 类，保持所有业务逻辑不变。
所有工具函数内联以消除循环依赖。
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import (
    MAX_SESSION_AGE,
    ADMIN_ACCOUNT,
    AI_OPTION_SUPPLEMENTS,
    DS_CONCEPTS,
)
from src.models.questions import ObjectiveQuestion, AssignmentQuestion


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

# ═══════════════════════════════════════════════════════════════
# 工具函数（内联避免循环依赖）
# ═══════════════════════════════════════════════════════════════


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, stored_hash = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
        return dk.hex() == stored_hash
    except (ValueError, AttributeError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_choice_answer(answer: Any) -> str:
    if isinstance(answer, list):
        answer = "".join(str(item) for item in answer)
    answer = unicodedata.normalize("NFKC", str(answer or "")).strip()
    compact = re.sub(r"[\s .。．,，:：;；、()（）\[\]【】]+", "", answer).upper()
    replacements = {
        "√": "A", "✓": "A", "✔": "A", "对": "A", "对的": "A",
        "是": "A", "是的": "A", "正确": "A", "正确的": "A",
        "YES": "A", "Y": "A", "TRUE": "A", "T": "A",
        "×": "B", "X": "B", "✕": "B", "✖": "B",
        "错": "B", "错的": "B", "否": "B", "不是": "B",
        "错误": "B", "错误的": "B", "不对": "B", "不正确": "B",
        "NO": "B", "N": "B", "FALSE": "B", "F": "B",
    }
    if compact in replacements:
        return replacements[compact]
    if any(marker in compact for marker in ("错误", "不正确", "不对", "错")):
        return "B"
    if any(marker in compact for marker in ("正确", "对", "√", "✓", "✔")):
        return "A"
    return re.sub(r"[^A-H]", "", compact)


def normalize_multi_answer(answer: Any) -> str:
    return "".join(sorted(set(normalize_choice_answer(answer))))


def normalize_fill(text: Any) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = re.sub(r"\(\s*\d+\s*\)", "", value)
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",").replace("；", ";").replace("：", ":")
    value = value.replace("×", "*").replace("＊", "*")
    value = re.sub(r"\s+", "", value)
    value = value.replace("＝", "=").replace("==", "=")
    return value.lower()


def fill_candidates(answer: str) -> list[str]:
    answer = answer.strip()
    parts = re.findall(r"\(\s*\d+\s*\)\s*([^\n]+)", answer)
    text = " ".join(parts) if parts else answer
    # “或/、”明确表示备选答案；斜杠只在中文词之间拆分，避免破坏数学公式。
    candidates = re.split(r"\s*(?:或|、)\s*", text)
    expanded = []
    for candidate in candidates:
        if re.search(r"[一-鿿]/[一-鿿]", candidate):
            expanded.extend(re.split(r"(?<=[一-鿿])/(?=[一-鿿])", candidate))
        else:
            expanded.append(candidate)
    candidates = expanded
    normalized = [normalize_fill(item) for item in candidates if normalize_fill(item)]
    return normalized or [normalize_fill(answer)]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def normalize_hash_text(text: str) -> str:
    text = normalize_space(text).lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[，。；：、,. ;:]", "", text)
    return text


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize_hash_text(text).encode("utf-8")).hexdigest()[:16]


def markers_match(text: str, markers: list[str]) -> bool:
    normalized = normalize_hash_text(text)
    return all(normalize_hash_text(marker) in normalized for marker in markers)


def extract_concepts_from_stem(stem: str) -> list[str]:
    matched = []
    stem_lower = stem.lower()
    for concept_category, keywords in DS_CONCEPTS.items():
        for kw in keywords:
            if kw.lower() in stem_lower:
                matched.append(concept_category)
                break
    return matched


def fsrs_schedule(stability: float, difficulty: float, is_correct: bool, interval_days: int = 0) -> tuple[float, float, int]:
    if is_correct:
        difficulty = max(0.0, difficulty - 0.1)
        stability = stability * (1.0 + 0.5 * (1.0 - difficulty))
    else:
        difficulty = min(1.0, difficulty + 0.2)
        stability = max(0.5, stability * 0.5)
    next_interval = stability * (1.0 - difficulty) * 7.0
    return stability, difficulty, max(1, int(next_interval))


def grade_answer(question: Any, user_answer: Any) -> dict[str, Any]:
    if question.qtype == "多选题":
        user_norm = normalize_multi_answer(user_answer)
        correct_norm = normalize_multi_answer(question.answer)
        is_correct = user_norm == correct_norm
    elif question.qtype == "判断题":
        user_norm = normalize_choice_answer(user_answer)
        correct_norm = normalize_choice_answer(question.answer)
        is_correct = bool(user_norm) and user_norm == correct_norm
    elif question.qtype == "单选题" and re.search(r"[A-H]", normalize_choice_answer(question.answer)):
        user_norm = normalize_choice_answer(user_answer)
        correct_norm = normalize_choice_answer(question.answer)
        is_correct = user_norm == correct_norm
    elif question.qtype == "填空题":
        user_norm = normalize_fill(user_answer)
        candidates = fill_candidates(question.answer)
        correct_norm = " / ".join(candidates)
        is_correct = user_norm in candidates
    else:
        user_norm = normalize_fill(user_answer)
        correct_norm = normalize_fill(question.answer)
        is_correct = user_norm == correct_norm

    analysis = _objective_analysis(question, is_correct)
    return {
        "is_correct": is_correct,
        "user_normalized": user_norm,
        "correct_normalized": correct_norm,
        "correct_answer": question.answer,
        "analysis": analysis,
    }


def _objective_analysis(question: Any, is_correct: bool) -> str:
    if getattr(question, "repaired", False):
        repair_note = "本题列入答案修复/校验表，已按题干确认标准答案。"
    else:
        repair_note = ""
    if is_correct:
        return f"答案正确。{repair_note}".strip()
    if question.qtype == "填空题":
        return f"答案不匹配。填空题已忽略空格、编号和常见符号差异。{repair_note}".strip()
    if question.qtype == "多选题":
        return "答案不匹配。多选题按选项集合比较，顺序不影响结果。"
    return f"答案不匹配，标准答案为 {question.answer}。{repair_note}".strip()


def option_supplement_for(question: Any) -> dict[str, Any] | None:
    for supplement in AI_OPTION_SUPPLEMENTS.values():
        markers = supplement.get("contains") or []
        if (
            markers
            and any(
                not option.get("text", "").strip()
                or option.get("text", "").strip() in {"O()", "o()"}
                for option in question.options
            )
            and markers_match(question.stem, markers)
        ):
            return supplement
    return AI_OPTION_SUPPLEMENTS.get(question.id)


IMAGE_RE = re.compile(r"\[IMAGE:([^\]]+)\]")
OPTION_RE = re.compile(r"^([A-H])\.\s*(.*)$")


def public_question(question: Any, include_answer: bool = False) -> dict[str, Any]:
    supplement = option_supplement_for(question)
    options = [dict(option) for option in question.options]
    if supplement:
        by_key = {option.get("key", ""): option for option in options}
        for key in supplement["options"]:
            if key not in by_key:
                option = {"key": key, "text": ""}
                options.append(option)
                by_key[key] = option
        options.sort(key=lambda item: item.get("key", ""))
        for option in options:
            key = option.get("key", "")
            if key in supplement["options"]:
                option["raw_text"] = option.get("text", "")
                option["text"] = supplement["options"][key]
                option["ai_supplemented"] = option["raw_text"] != option["text"]
    payload = {
        "bank_id": "exam",
        "id": question.id,
        "source_order": question.source_order,
        "source_num": question.source_num,
        "qtype": question.qtype,
        "chapter": question.chapter,
        "stem": question.stem,
        "options": options,
        "score": question.score,
        "images": question.images,
        "repaired": question.repaired,
        "suspicious": question.suspicious,
        "stem_hash": question.stem_hash,
        "ai_completed": bool(supplement),
        "completion_note": supplement["note"] if supplement else "",
    }
    if supplement:
        payload["original_options"] = question.options
    if include_answer:
        payload["answer"] = question.answer
        payload["raw_correct"] = question.raw_correct
    return payload


def public_assignment_question(question: Any, include_answer: bool = True) -> dict[str, Any]:
    payload = {
        "bank_id": "assignment",
        "id": question.id,
        "source_order": question.source_order,
        "source_num": question.source_num,
        "qtype": question.qtype,
        "chapter": question.chapter,
        "stem": question.stem,
        "options": [dict(option) for option in question.options],
        "images": question.images,
        "suspicious": question.suspicious,
        "stem_hash": question.stem_hash,
        "answer_source": question.answer_source,
        "answer_available": bool(question.answer),
    }
    if include_answer:
        payload["answer"] = question.answer
        payload["raw_correct"] = question.raw_correct
    return payload


def public_bank_question(question: Any, include_answer: bool = False) -> dict[str, Any]:
    if hasattr(question, "answer_source"):  # AssignmentQuestion
        return public_assignment_question(question, include_answer=True)
    return public_question(question, include_answer=include_answer)


def public_discussion(question: Any) -> dict[str, Any]:
    return {
        "id": question.id,
        "source_order": question.source_order,
        "chapter": question.chapter,
        "prompt": question.prompt,
        "stem_hash": question.stem_hash,
    }


# ═══════════════════════════════════════════════════════════════
# PracticeDatabase
# ═══════════════════════════════════════════════════════════════


class PracticeDatabase:
    """SQLite 数据库封装 —— 练习记录、用户系统、画像、社区。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    qtype TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS ai_questions (
                    id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    source_question_id INTEGER NOT NULL,
                    qtype TEXT NOT NULL,
                    stem TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    analysis TEXT NOT NULL,
                    stem_hash TEXT,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS discussion_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discussion_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS assignment_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    answer_source TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    user_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    role TEXT DEFAULT 'student',
                    status TEXT DEFAULT 'pending',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS user_profile (
                    user_id INTEGER PRIMARY KEY,
                    chapter_accuracy_json TEXT DEFAULT '{}',
                    type_accuracy_json TEXT DEFAULT '{}',
                    weak_concepts_json TEXT DEFAULT '[]',
                    strong_concepts_json TEXT DEFAULT '[]',
                    total_attempts INTEGER DEFAULT 0,
                    total_correct INTEGER DEFAULT 0,
                    practice_streak INTEGER DEFAULT 0,
                    last_practice_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER,
                    mode TEXT DEFAULT 'tutor',
                    messages_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS generated_questions (
                    stem_hash TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    account TEXT NOT NULL,
                    ip TEXT,
                    success INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS custom_banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    questions_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    FOREIGN KEY (owner_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS learning_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_data_json TEXT NOT NULL DEFAULT '{}',
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    exam_date TEXT,
                    daily_minutes INTEGER,
                    timezone TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS community_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER,
                    bank_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS community_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES community_posts(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS concept_mastery (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    concept TEXT NOT NULL,
                    mastery_score REAL DEFAULT 0.5,
                    total_attempts INTEGER DEFAULT 0,
                    correct_attempts INTEGER DEFAULT 0,
                    last_review_at REAL,
                    next_review_at REAL,
                    stability REAL DEFAULT 1.0,
                    difficulty REAL DEFAULT 0.3,
                    created_at REAL NOT NULL,
                    updated_at REAL,
                    UNIQUE(user_id, concept)
                );
                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    bank_id TEXT NOT NULL,
                    session_id TEXT,
                    attempt_token TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    normalized_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    qtype TEXT NOT NULL,
                    chapter TEXT NOT NULL,
                    time_spent_seconds REAL DEFAULT 0,
                    concept_weights_json TEXT NOT NULL,
                    error_reason_rule_json TEXT NOT NULL,
                    error_reason_ai_json TEXT,
                    error_reason_final_json TEXT NOT NULL,
                    recommendation_snapshot_id TEXT,
                    rule_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    response_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_learning_events_user_attempt_token
                    ON learning_events(user_id, attempt_token);
                CREATE INDEX IF NOT EXISTS ix_learning_events_user_created
                    ON learning_events(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS question_concepts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    bank_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    role TEXT NOT NULL,
                    weight REAL NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    mapping_version TEXT NOT NULL,
                    UNIQUE(question_id, bank_id, concept)
                );
                CREATE TABLE IF NOT EXISTS mastery_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learning_event_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    concept TEXT NOT NULL,
                    role TEXT NOT NULL,
                    weight REAL NOT NULL,
                    before_score REAL NOT NULL,
                    after_score REAL NOT NULL,
                    delta REAL NOT NULL,
                    before_stability REAL NOT NULL,
                    after_stability REAL NOT NULL,
                    before_difficulty REAL NOT NULL,
                    after_difficulty REAL NOT NULL,
                    evidence_json TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_mastery_changes_event
                    ON mastery_changes(learning_event_id);
                CREATE TABLE IF NOT EXISTS review_feedback (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    concept TEXT NOT NULL,
                    learning_event_id TEXT,
                    feedback TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_review_feedback_user_concept
                    ON review_feedback(user_id, concept, created_at DESC);
                CREATE TABLE IF NOT EXISTS recommendation_snapshots (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    learning_event_id TEXT NOT NULL,
                    selected_question_id INTEGER NOT NULL,
                    bank_id TEXT NOT NULL,
                    recommendation_type TEXT NOT NULL,
                    score_breakdown_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    student_explanation TEXT NOT NULL,
                    total_score REAL NOT NULL,
                    rule_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_recommendation_snapshots_user_created
                    ON recommendation_snapshots(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    summary_rule_json TEXT NOT NULL,
                    summary_ai_json TEXT,
                    summary_final_json TEXT NOT NULL,
                    generation_method TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, conversation_id)
                );
                CREATE TABLE IF NOT EXISTS learning_notes (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    auto_content_json TEXT,
                    user_content TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    concept TEXT,
                    error_category TEXT,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_learning_notes_user_updated
                    ON learning_notes(user_id, is_archived, updated_at DESC);
                """
            )
            # 迁移：为旧表添加列
            _allowed_tables = {
                "attempts", "ai_questions", "discussion_feedback", "assignment_feedback",
            }
            for table in _allowed_tables:
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
            try:
                db.execute("ALTER TABLE attempts ADD COLUMN chapter TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                db.execute("ALTER TABLE ai_questions ADD COLUMN stem_hash TEXT")
            except sqlite3.OperationalError:
                pass
            for column, definition in (
                ("review_state", "TEXT DEFAULT 'new'"),
                ("last_learning_event_id", "TEXT"),
                ("rule_version", "TEXT DEFAULT 'learning-loop-v1'"),
            ):
                existing_columns = {
                    row[1] for row in db.execute("PRAGMA table_info(concept_mastery)").fetchall()
                }
                if column not in existing_columns:
                    db.execute(f"ALTER TABLE concept_mastery ADD COLUMN {column} {definition}")
            plan_columns = {
                row[1] for row in db.execute("PRAGMA table_info(learning_plans)").fetchall()
            }
            for column, definition in (
                ("version", "INTEGER NOT NULL DEFAULT 1"),
                ("status", "TEXT NOT NULL DEFAULT 'active'"),
                ("exam_date", "TEXT"),
                ("daily_minutes", "INTEGER"),
                ("timezone", "TEXT"),
            ):
                if column not in plan_columns:
                    db.execute(f"ALTER TABLE learning_plans ADD COLUMN {column} {definition}")
            legacy_ai_questions = db.execute(
                "SELECT id, stem FROM ai_questions WHERE stem_hash IS NULL OR stem_hash = ''"
            ).fetchall()
            for row in legacy_ai_questions:
                db.execute(
                    "UPDATE ai_questions SET stem_hash = ? WHERE id = ?",
                    (text_hash(row["stem"]), row["id"]),
                )

    # ── 练习记录 ──

    def record_attempt(
        self,
        question_id: int,
        source: str,
        qtype: str,
        user_answer: Any,
        correct_answer: str,
        is_correct: bool,
        user_id: int = 0,
        chapter: str = "",
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO attempts
                    (question_id, source, qtype, user_answer, correct_answer, is_correct, created_at, user_id, chapter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    question_id, source, qtype,
                    json.dumps(user_answer, ensure_ascii=False),
                    correct_answer, 1 if is_correct else 0, time.time(),
                    user_id, chapter,
                ),
            )

    def record_ai_question(
        self, item: dict[str, Any], model: str, source_question_id: int,
    ) -> str:
        ai_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """INSERT INTO ai_questions
                    (id, model, source_question_id, qtype, stem, options_json,
                     answer, analysis, stem_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ai_id, model, source_question_id, item["qtype"], item["stem"],
                    json.dumps(item.get("options", []), ensure_ascii=False),
                    item["answer"], item.get("analysis", ""),
                    text_hash(item["stem"]), time.time(),
                ),
            )
        return ai_id

    def get_ai_question(self, ai_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM ai_questions WHERE id = ?", (ai_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "model": row["model"],
            "source_question_id": row["source_question_id"],
            "qtype": row["qtype"], "stem": row["stem"],
            "options": json.loads(row["options_json"]),
            "answer": row["answer"], "analysis": row["analysis"],
            "created_at": row["created_at"],
        }

    def record_discussion_feedback(
        self, discussion_id: int, model: str, user_answer: str, feedback: dict[str, Any],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO discussion_feedback
                    (discussion_id, model, user_answer, feedback_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (discussion_id, model, user_answer, json.dumps(feedback, ensure_ascii=False), time.time()),
            )

    def record_assignment_feedback(
        self, question_id: int, model: str, answer_source: str,
        user_answer: str, feedback: dict[str, Any],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO assignment_feedback
                    (question_id, model, answer_source, user_answer, feedback_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (question_id, model, answer_source, user_answer,
                 json.dumps(feedback, ensure_ascii=False), time.time()),
            )

    # ── 错题本 ──

    def wrong_attempts(self, bank, limit: int = 80) -> list[dict[str, Any]]:
        questions = bank.by_id
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM attempts
                WHERE is_correct = 0 AND source IN ('bank', 'exam')
                ORDER BY created_at DESC LIMIT ?""",
                (limit * 4,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        seen: set[int] = set()
        for row in rows:
            if row["question_id"] in seen:
                continue
            question = questions.get(row["question_id"])
            if not question:
                continue
            seen.add(row["question_id"])
            items.append({
                "attempt_id": row["id"],
                "question": public_question(question, include_answer=True),
                "user_answer": json.loads(row["user_answer"]),
                "created_at": row["created_at"],
            })
            if len(items) >= limit:
                break
        return items

    def summary(self, source: str = "exam", user_id: int = 0) -> dict[str, int]:
        if source == "exam":
            where = "source IN ('bank', 'exam')"
            params: list[Any] = []
        else:
            where = "source = ?"
            params = [source]
        if user_id > 0:
            where += " AND user_id = ?"
            params.append(user_id)
        with self.connect() as db:
            row = db.execute(
                f"""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct,
                    SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS wrong
                FROM attempts WHERE {where}""",
                tuple(params),
            ).fetchone()
        return {
            "attempts": int(row["total"] or 0),
            "correct": int(row["correct"] or 0),
            "wrong": int(row["wrong"] or 0),
        }

    # ── 概念掌握度 ──

    def update_concept_mastery(self, user_id: int, concept: str, is_correct: bool) -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM concept_mastery WHERE user_id = ? AND concept = ?",
                (user_id, concept),
            ).fetchone()
            if row:
                old_score = row["mastery_score"]
                total = row["total_attempts"] + 1
                correct = row["correct_attempts"] + (1 if is_correct else 0)
                alpha = 0.3
                new_score = old_score + alpha * ((1.0 if is_correct else 0.0) - old_score)
                new_score = round(max(0.0, min(1.0, new_score)), 4)
                stability = row["stability"]
                difficulty = row["difficulty"]
                interval_days = (
                    max(0, int((now - row["last_review_at"]) / 86400))
                    if row["last_review_at"] else 0
                )
                stability, difficulty, next_interval = fsrs_schedule(
                    stability, difficulty, is_correct, interval_days,
                )
                next_review = now + next_interval * 86400
                db.execute(
                    """UPDATE concept_mastery SET
                       mastery_score = ?, total_attempts = ?, correct_attempts = ?,
                       last_review_at = ?, next_review_at = ?,
                       stability = ?, difficulty = ?, updated_at = ?
                       WHERE user_id = ? AND concept = ?""",
                    (new_score, total, correct, now, next_review, stability, difficulty, now, user_id, concept),
                )
                return {"concept": concept, "mastery_score": new_score, "total_attempts": total, "next_review_at": next_review}
            else:
                stability = 1.0
                difficulty = 0.3
                _, _, next_interval = fsrs_schedule(stability, difficulty, is_correct, 0)
                next_review = now + next_interval * 86400
                new_score = 0.65 if is_correct else 0.35
                db.execute(
                    """INSERT INTO concept_mastery
                       (user_id, concept, mastery_score, total_attempts, correct_attempts,
                        last_review_at, next_review_at, stability, difficulty, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, concept, new_score, 1, 1 if is_correct else 0,
                     now, next_review, stability, difficulty, now, now),
                )
                return {"concept": concept, "mastery_score": new_score, "total_attempts": 1, "next_review_at": next_review}

    def get_concept_mastery(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM concept_mastery WHERE user_id = ? ORDER BY mastery_score ASC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_spaced_practice(self, user_id: int, count: int, bank) -> dict[str, Any]:
        now = time.time()
        with self.connect() as db:
            rows = db.execute(
                """SELECT concept FROM concept_mastery
                   WHERE user_id = ? AND next_review_at <= ?
                   ORDER BY mastery_score ASC LIMIT ?""",
                (user_id, now, count * 3),
            ).fetchall()
        due_concepts = [r["concept"] for r in rows] if rows else []
        if not due_concepts:
            return {"questions": [], "reason": "当前没有需要复习的概念，请继续保持！", "mode": "spaced_practice"}

        matched = []
        for q in bank.questions:
            q_concepts = extract_concepts_from_stem(q.stem)
            if any(c in due_concepts for c in q_concepts):
                matched.append(q)
        if not matched:
            return {"questions": [], "reason": "未找到匹配的复习题目。", "mode": "spaced_practice"}

        selected = random.sample(matched, min(count, len(matched)))
        return {
            "questions": [public_bank_question(q) for q in selected],
            "count": len(selected),
            "mode": "spaced_practice",
            "due_concepts": due_concepts[:10],
        }

    def commit_learning_event(self, draft: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
        from src.learning.repository import LearningRepository
        return LearningRepository(self).commit_learning_event(draft, outcome)

    def get_learning_event(self, user_id: int, event_id: str) -> dict[str, Any]:
        from src.learning.repository import LearningRepository
        return LearningRepository(self).get_learning_event(user_id, event_id)

    def get_due_reviews(self, user_id: int, evaluated_at: str) -> list[dict[str, Any]]:
        from src.learning.repository import LearningRepository
        return LearningRepository(self).get_due_reviews(user_id, evaluated_at)

    def save_review_feedback(
        self,
        user_id: int,
        concept: str,
        feedback: str,
        learning_event_id: str | None,
        reviewed_at: str,
        next_review_at: str,
    ) -> dict[str, Any]:
        from src.learning.repository import LearningRepository
        return LearningRepository(self).save_review_feedback(
            user_id, concept, feedback, learning_event_id, reviewed_at, next_review_at,
        )

    # ── 用户系统 ──

    def create_user(self, account: str, password: str, name: str, phone: str) -> dict[str, Any]:
        with self.connect() as db:
            existing = db.execute("SELECT id FROM users WHERE account = ?", (account,)).fetchone()
            if existing:
                raise ValueError("该账号已被注册。")
            password_hash = hash_password(password)
            now = time.time()
            # 普通创建路径永远不能提升权限；管理员只能由 ensure_admin 引导。
            role = "student"
            status = "pending"
            cursor = db.execute(
                """INSERT INTO users (account, password_hash, name, phone, role, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account, password_hash, name, phone, role, status, now),
            )
            user_id = cursor.lastrowid
            db.execute(
                "INSERT OR IGNORE INTO user_profile (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            return {
                "id": user_id, "account": account, "name": name,
                "phone": phone, "role": role, "status": status,
            }

    def ensure_admin(self, account: str, password: str, name: str, phone: str) -> dict[str, Any]:
        """Create or reconcile the configured administrator account."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE account = ?", (account,)).fetchone()
            if not row:
                password_hash = hash_password(password)
                now = time.time()
                cursor = db.execute(
                    """INSERT INTO users (account, password_hash, name, phone, role, status, created_at)
                       VALUES (?, ?, ?, ?, 'admin', 'approved', ?)""",
                    (account, password_hash, name, phone, now),
                )
                user_id = cursor.lastrowid
                db.execute(
                    "INSERT OR IGNORE INTO user_profile (user_id, updated_at) VALUES (?, ?)",
                    (user_id, now),
                )
            else:
                user_id = row["id"]
                credentials_changed = not verify_password(password, row["password_hash"])
                privileges_changed = row["role"] != "admin" or row["status"] != "approved"
                password_hash = hash_password(password) if credentials_changed else row["password_hash"]
                db.execute(
                    """UPDATE users
                       SET password_hash = ?, role = 'admin', status = 'approved'
                       WHERE id = ?""",
                    (password_hash, user_id),
                )
                if credentials_changed or privileges_changed:
                    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

            # The configured administrator must be recoverable after a password
            # rotation or stale failed-attempt records from an older deployment.
            db.execute(
                "DELETE FROM login_attempts WHERE account = ? AND success = 0",
                (account,),
            )

            current = db.execute(
                "SELECT id, account, name, phone, role, status FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(current)

    def authenticate(self, account: str, password: str, ip: str = "") -> dict[str, Any] | None:
        if self.is_account_locked(account):
            raise PermissionError("该账号因多次登录失败已被临时锁定，请30分钟后再试。")
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE account = ?", (account,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                self.record_login_attempt(account, ip, False)
                return None
            self.record_login_attempt(account, ip, True)
            return {
                "id": row["id"], "account": row["account"],
                "name": row["name"], "phone": row["phone"],
                "role": row["role"], "status": row["status"],
            }

    def record_login_attempt(self, account: str, ip: str, success: bool) -> None:
        with self.connect() as db:
            if success:
                db.execute(
                    "DELETE FROM login_attempts WHERE account = ? AND success = 0",
                    (account,),
                )
            db.execute(
                "INSERT INTO login_attempts (account, ip, success, created_at) VALUES (?, ?, ?, ?)",
                (account, ip, 1 if success else 0, time.time()),
            )

    def is_account_locked(self, account: str) -> bool:
        cutoff = time.time() - 1800
        with self.connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS cnt FROM login_attempts
                   WHERE account = ? AND success = 0 AND created_at > ?""",
                (account, cutoff),
            ).fetchone()
            if row and row["cnt"] >= 5:
                last = db.execute(
                    "SELECT created_at FROM login_attempts WHERE account = ? AND success = 0 ORDER BY created_at DESC LIMIT 1",
                    (account,),
                ).fetchone()
                if last and (time.time() - last["created_at"]) < 1800:
                    return True
            return False

    def cleanup_old_login_attempts(self) -> int:
        cutoff = time.time() - 3600
        with self.connect() as db:
            result = db.execute("DELETE FROM login_attempts WHERE created_at < ?", (cutoff,))
            return result.rowcount

    def create_session(self, user_id: int) -> str:
        token = generate_token()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, time.time()),
            )
        return token

    def get_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT s.token, s.user_id, s.created_at, u.account, u.name, u.role, u.status, u.phone
                   FROM sessions s JOIN users u ON s.user_id = u.id
                   WHERE s.token = ?""",
                (token,),
            ).fetchone()
            if not row:
                return None
            if time.time() - row["created_at"] > MAX_SESSION_AGE:
                db.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
            return {
                "token": row["token"], "user_id": row["user_id"],
                "account": row["account"], "name": row["name"],
                "role": row["role"], "status": row["status"],
                "phone": row["phone"],
            }

    def cleanup_expired_sessions(self) -> int:
        cutoff = time.time() - MAX_SESSION_AGE
        with self.connect() as db:
            result = db.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            return result.rowcount

    def delete_session(self, token: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    # ── 自定义题库 ──

    def create_custom_bank(self, name: str, owner_id: int, questions_json: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO custom_banks (name, owner_id, questions_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (name, owner_id, questions_json, time.time()),
            )
            return cursor.lastrowid

    def list_custom_banks(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb JOIN users u ON cb.owner_id = u.id
                   WHERE cb.owner_id = ? ORDER BY cb.created_at DESC""",
                (user_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"], "name": row["name"],
                    "owner_id": row["owner_id"], "owner_name": row["owner_name"],
                    "questions_json": row["questions_json"], "created_at": row["created_at"],
                }
                for row in rows
            ]

    def list_public_banks(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb JOIN users u ON cb.owner_id = u.id
                   ORDER BY cb.created_at DESC LIMIT 100"""
            ).fetchall()
            return [
                {
                    "id": row["id"], "name": row["name"],
                    "owner_id": row["owner_id"], "owner_name": row["owner_name"],
                    "questions_json": row["questions_json"], "created_at": row["created_at"],
                }
                for row in rows
            ]

    def get_custom_bank(self, bank_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT cb.*, u.name AS owner_name
                   FROM custom_banks cb JOIN users u ON cb.owner_id = u.id
                   WHERE cb.id = ?""",
                (bank_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"], "name": row["name"],
                "owner_id": row["owner_id"], "owner_name": row["owner_name"],
                "questions_json": row["questions_json"], "created_at": row["created_at"],
            }

    # ── 管理员 ──

    def get_pending_users(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, account, name, phone, role, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def approve_user(self, user_id: int, approved: bool) -> dict[str, Any]:
        status = "approved" if approved else "rejected"
        with self.connect() as db:
            db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            row = db.execute("SELECT id, account, name, phone, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise KeyError("用户不存在。")
            return dict(row)

    def get_all_users(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, account, name, phone, role, status, created_at FROM users ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    # ── 用户画像 ──

    def update_user_profile(self, user_id: int) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT a.is_correct, a.source, a.qtype, a.question_id, a.chapter
                   FROM attempts a WHERE a.user_id = ? AND a.source != 'ai'
                   ORDER BY a.created_at DESC LIMIT 500""",
                (user_id,),
            ).fetchall()

        total = len(rows)
        correct = sum(1 for r in rows if r["is_correct"])
        chapter_stats: dict[str, list[int]] = {}
        type_stats: dict[str, list[int]] = {}

        for r in rows:
            qtype = r["qtype"]
            if qtype not in type_stats:
                type_stats[qtype] = []
            type_stats[qtype].append(1 if r["is_correct"] else 0)
            ch = (r["chapter"] or "未分章").strip()
            if ch:
                if ch not in chapter_stats:
                    chapter_stats[ch] = []
                chapter_stats[ch].append(1 if r["is_correct"] else 0)

        chapter_accuracy = {
            ch: round(sum(vals) / len(vals), 3) if vals else 0
            for ch, vals in chapter_stats.items()
        }
        type_accuracy = {
            t: round(sum(vals) / len(vals), 3) if vals else 0
            for t, vals in type_stats.items()
        }

        weak_concepts = sorted(
            [ch for ch, acc in chapter_accuracy.items() if acc < 0.5],
            key=lambda ch: chapter_accuracy[ch],
        )[:5]
        strong_concepts = sorted(
            [ch for ch, acc in chapter_accuracy.items() if acc >= 0.8 and sum(chapter_stats.get(ch, [])) >= 5],
            key=lambda ch: -chapter_accuracy[ch],
        )[:5]

        now = time.time()
        with self.connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO user_profile
                   (user_id, chapter_accuracy_json, type_accuracy_json, weak_concepts_json,
                    strong_concepts_json, total_attempts, total_correct, last_practice_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    json.dumps(chapter_accuracy, ensure_ascii=False),
                    json.dumps(type_accuracy, ensure_ascii=False),
                    json.dumps(weak_concepts, ensure_ascii=False),
                    json.dumps(strong_concepts, ensure_ascii=False),
                    total, correct, now, now,
                ),
            )

        return {
            "user_id": user_id,
            "total_attempts": total, "total_correct": correct,
            "accuracy": round(correct / total, 3) if total > 0 else 0,
            "type_accuracy": type_accuracy,
            "weak_concepts": weak_concepts, "strong_concepts": strong_concepts,
        }

    def get_user_profile(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "chapter_accuracy": json.loads(row["chapter_accuracy_json"]),
                "type_accuracy": json.loads(row["type_accuracy_json"]),
                "weak_concepts": json.loads(row["weak_concepts_json"]),
                "strong_concepts": json.loads(row["strong_concepts_json"]),
                "total_attempts": row["total_attempts"],
                "total_correct": row["total_correct"],
                "practice_streak": row["practice_streak"],
                "last_practice_at": row["last_practice_at"],
            }

    # ── 去重 ──

    def is_question_duplicate(self, stem_hash: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT 1 FROM generated_questions WHERE stem_hash = ?", (stem_hash,)).fetchone()
            return bool(row)

    def record_generated_question(self, stem_hash: str, question_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO generated_questions (stem_hash, question_id, created_at) VALUES (?, ?, ?)",
                (stem_hash, question_id, time.time()),
            )

    # ── AI 对话 ──

    def save_conversation(self, user_id: int, question_id: int | None, mode: str, messages: list[dict[str, str]]) -> int:
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO ai_conversations (user_id, question_id, mode, messages_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, question_id, mode, json.dumps(messages, ensure_ascii=False), now, now),
            )
            return cursor.lastrowid

    def get_conversations(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM ai_conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"], "user_id": row["user_id"],
                    "question_id": row["question_id"], "mode": row["mode"],
                    "messages": json.loads(row["messages_json"]),
                    "created_at": row["created_at"], "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def get_conversation(self, conversation_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM ai_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"], "user_id": row["user_id"],
                "question_id": row["question_id"], "mode": row["mode"],
                "messages": json.loads(row["messages_json"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"],
            }

    def update_conversation(
        self,
        conversation_id: int,
        user_id: int,
        messages: list[dict[str, str]],
    ) -> None:
        with self.connect() as db:
            result = db.execute(
                """UPDATE ai_conversations SET messages_json = ?, updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (json.dumps(messages, ensure_ascii=False), time.time(), conversation_id, user_id),
            )
            if result.rowcount != 1:
                raise KeyError("对话不存在。")

    def get_all_question_stems_and_hashes(self) -> list[str]:
        hashes: set[str] = set()
        with self.connect() as db:
            rows = db.execute("SELECT stem_hash FROM ai_questions").fetchall()
            for row in rows:
                if row["stem_hash"]:
                    hashes.add(row["stem_hash"])
            rows = db.execute("SELECT stem_hash FROM generated_questions").fetchall()
            for row in rows:
                if row["stem_hash"]:
                    hashes.add(row["stem_hash"])
        return list(hashes)

    # ── 学习计划 ──

    def create_learning_plan(self, user_id: int, plan_data: dict[str, Any]) -> int:
        now = time.time()
        with self.connect() as db:
            current = db.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM learning_plans WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version = int(current["version"] or 0) + 1
            db.execute(
                "UPDATE learning_plans SET status = 'superseded', updated_at = ? WHERE user_id = ? AND status != 'superseded'",
                (now, user_id),
            )
            cursor = db.execute(
                """INSERT INTO learning_plans
                   (user_id, plan_data_json, version, status, exam_date, daily_minutes,
                    timezone, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, json.dumps(plan_data, ensure_ascii=False), version,
                 plan_data.get("status", "active"), plan_data.get("exam_date"),
                 plan_data.get("daily_minutes"), plan_data.get("timezone"), now, now),
            )
            return cursor.lastrowid

    def get_learning_plan(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM learning_plans WHERE user_id = ? AND status != 'superseded' ORDER BY version DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            plan_data = json.loads(row["plan_data_json"])
            for day in plan_data.get("days", []):
                completed = 0
                for target in day.get("targets", []):
                    actual = db.execute(
                        """SELECT COUNT(*) AS cnt FROM attempts
                           WHERE user_id = ? AND source = ? AND created_at > ? AND created_at < ?""",
                        (user_id, target.get("source", "exam"),
                         row["created_at"] + day.get("day_index", 0) * 86400,
                         row["created_at"] + (day.get("day_index", 0) + 1) * 86400),
                    ).fetchone()
                    target["completed"] = actual["cnt"] if actual else 0
                    completed += min(target["completed"], target.get("target_count", 0))
                total_target = sum(t.get("target_count", 0) for t in day.get("targets", []))
                day["progress"] = round(completed / total_target, 3) if total_target > 0 else 0
            return {
                "id": row["id"], "user_id": row["user_id"],
                "version": row["version"], "status": row["status"],
                "exam_date": row["exam_date"], "daily_minutes": row["daily_minutes"],
                "timezone": row["timezone"],
                "plan_data": plan_data,
                "created_at": row["created_at"], "updated_at": row["updated_at"],
            }

    def get_learning_plan_history(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM learning_plans WHERE user_id = ? ORDER BY version DESC",
                (user_id,),
            ).fetchall()
        return [{
            "id": row["id"], "user_id": row["user_id"], "version": row["version"],
            "status": row["status"], "exam_date": row["exam_date"],
            "daily_minutes": row["daily_minutes"], "timezone": row["timezone"],
            "plan_data": json.loads(row["plan_data_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        } for row in rows]

    def refresh_conversation_summary(
        self, user_id: int, conversation_id: int, known_concepts: list[str],
    ) -> dict[str, Any]:
        from src.learning.contracts import RULE_VERSION
        from src.learning.rules import summarize_conversation

        conversation = self.get_conversation(conversation_id, user_id)
        if not conversation:
            raise KeyError("对话不存在。")
        messages = [
            {**message, "id": message.get("id") or f"{conversation_id}:{index + 1}"}
            for index, message in enumerate(conversation["messages"])
        ]
        summary = summarize_conversation(messages, known_concepts)
        now = _utc_iso_now()
        summary_id = str(uuid.uuid4())
        encoded = json.dumps(summary, ensure_ascii=False)
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM conversation_summaries WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id),
            ).fetchone()
            if existing:
                summary_id = existing["id"]
                db.execute(
                    """UPDATE conversation_summaries SET summary_rule_json = ?, summary_final_json = ?,
                       generation_method = 'rule', rule_version = ?, updated_at = ? WHERE id = ?""",
                    (encoded, encoded, RULE_VERSION, now, summary_id),
                )
            else:
                db.execute(
                    """INSERT INTO conversation_summaries
                       (id, user_id, conversation_id, summary_rule_json, summary_final_json,
                        generation_method, rule_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'rule', ?, ?, ?)""",
                    (summary_id, user_id, conversation_id, encoded, encoded, RULE_VERSION, now, now),
                )
        return {"id": summary_id, "conversation_id": conversation_id,
                "summary_rule": summary, "summary_final": summary,
                "generation_method": "rule", "rule_version": RULE_VERSION}

    def create_learning_note(
        self, user_id: int, title: str, user_content: str = "", tags: list[str] | None = None,
        concept: str | None = None,
    ) -> dict[str, Any]:
        note_id = str(uuid.uuid4())
        now = _utc_iso_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO learning_notes
                   (id, user_id, title, user_content, tags_json, source_type, concept, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, ?)""",
                (note_id, user_id, title, user_content, json.dumps(tags or [], ensure_ascii=False), concept, now, now),
            )
        return self.get_learning_note(user_id, note_id)

    def get_learning_note(self, user_id: int, note_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM learning_notes WHERE id = ? AND user_id = ?", (note_id, user_id),
            ).fetchone()
        if not row:
            raise KeyError("学习笔记不存在。")
        item = dict(row)
        item["auto_content"] = json.loads(item.pop("auto_content_json") or "null")
        item["tags"] = json.loads(item.pop("tags_json") or "[]")
        item["is_pinned"] = bool(item["is_pinned"])
        item["is_archived"] = bool(item["is_archived"])
        return item

    def list_learning_notes(
        self, user_id: int, *, archived: bool = False, source_type: str | None = None,
        concept: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["user_id = ?", "is_archived = ?"]
        params: list[Any] = [user_id, 1 if archived else 0]
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if concept:
            conditions.append("concept = ?")
            params.append(concept)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT id FROM learning_notes WHERE {' AND '.join(conditions)} ORDER BY is_pinned DESC, updated_at DESC",
                params,
            ).fetchall()
        return [self.get_learning_note(user_id, row["id"]) for row in rows]

    def update_learning_note(self, user_id: int, note_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.get_learning_note(user_id, note_id)
        allowed = {"title", "user_content", "concept", "is_pinned", "is_archived"}
        values = {key: value for key, value in changes.items() if key in allowed and value is not None}
        if changes.get("tags") is not None:
            values["tags_json"] = json.dumps(changes["tags"], ensure_ascii=False)
        if not values:
            return self.get_learning_note(user_id, note_id)
        values["updated_at"] = _utc_iso_now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as db:
            db.execute(
                f"UPDATE learning_notes SET {assignments} WHERE id = ? AND user_id = ?",
                [*values.values(), note_id, user_id],
            )
        return self.get_learning_note(user_id, note_id)

    # ── 社区 ──

    def create_post(self, user_id: int, question_id: int | None, bank_id: str | None,
                    title: str, content: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO community_posts (user_id, question_id, bank_id, title, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, question_id, bank_id, title, content, time.time()),
            )
            return cursor.lastrowid

    def get_posts(self, question_id: int | None = None, bank_id: str | None = None,
                  limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as db:
            conditions = []
            params: list[Any] = []
            if question_id is not None:
                conditions.append("p.question_id = ?")
                params.append(question_id)
            if bank_id is not None:
                conditions.append("p.bank_id = ?")
                params.append(bank_id)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.extend([limit, offset])
            rows = db.execute(
                f"""SELECT p.*, u.name AS author_name, u.account AS author_account
                    FROM community_posts p JOIN users u ON p.user_id = u.id
                    {where} ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
                params,
            ).fetchall()
            posts = []
            for row in rows:
                replies = db.execute(
                    """SELECT r.*, u.name AS author_name, u.account AS author_account
                       FROM community_replies r JOIN users u ON r.user_id = u.id
                       WHERE r.post_id = ? ORDER BY r.created_at ASC""",
                    (row["id"],),
                ).fetchall()
                posts.append({
                    "id": row["id"], "user_id": row["user_id"],
                    "author_name": row["author_name"], "author_account": row["author_account"],
                    "question_id": row["question_id"], "bank_id": row["bank_id"],
                    "title": row["title"], "content": row["content"],
                    "created_at": row["created_at"],
                    "replies": [
                        {
                            "id": r["id"], "post_id": r["post_id"],
                            "user_id": r["user_id"],
                            "author_name": r["author_name"],
                            "author_account": r["author_account"],
                            "content": r["content"], "created_at": r["created_at"],
                        }
                        for r in replies
                    ],
                })
            return posts

    def create_reply(self, post_id: int, user_id: int, content: str) -> int:
        with self.connect() as db:
            post = db.execute("SELECT id FROM community_posts WHERE id = ?", (post_id,)).fetchone()
            if not post:
                raise KeyError("帖子不存在。")
            cursor = db.execute(
                """INSERT INTO community_replies (post_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (post_id, user_id, content, time.time()),
            )
            return cursor.lastrowid

    # ── 排行榜 ──

    def get_leaderboard(self, period: str = "week") -> list[dict[str, Any]]:
        if period == "month":
            cutoff = time.time() - 86400 * 30
        else:
            cutoff = time.time() - 86400 * 7
        with self.connect() as db:
            rows = db.execute(
                """SELECT a.user_id, u.name, u.account,
                          COUNT(*) AS practice_count,
                          SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
                   FROM attempts a JOIN users u ON a.user_id = u.id
                   WHERE a.created_at > ? AND a.user_id > 0
                   GROUP BY a.user_id ORDER BY practice_count DESC LIMIT 50""",
                (cutoff,),
            ).fetchall()
            return [
                {
                    "rank": i + 1, "user_id": row["user_id"],
                    "name": row["name"], "account": row["account"],
                    "practice_count": row["practice_count"],
                    "correct_count": row["correct_count"],
                    "accuracy": round(row["correct_count"] / row["practice_count"], 3)
                    if row["practice_count"] > 0 else 0,
                }
                for i, row in enumerate(rows)
            ]

    # ── 学习报告 ──

    def get_learning_report_data(self, user_id: int) -> dict[str, Any]:
        profile = self.get_user_profile(user_id) or {}
        with self.connect() as db:
            user = db.execute("SELECT name, account, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
            type_rows = db.execute(
                """SELECT a.qtype, a.is_correct, COUNT(*) AS cnt
                   FROM attempts a WHERE a.user_id = ? AND a.source != 'ai'
                   GROUP BY a.qtype, a.is_correct""",
                (user_id,),
            ).fetchall()
            recent = db.execute(
                "SELECT a.* FROM attempts a WHERE a.user_id = ? ORDER BY a.created_at DESC LIMIT 20",
                (user_id,),
            ).fetchall()

        total_attempts = sum(r["cnt"] for r in type_rows)
        total_correct = sum(r["cnt"] for r in type_rows if r["is_correct"])
        type_accuracy: dict[str, dict[str, int]] = {}
        for r in type_rows:
            qtype = r["qtype"]
            if qtype not in type_accuracy:
                type_accuracy[qtype] = {"correct": 0, "total": 0}
            type_accuracy[qtype]["total"] += r["cnt"]
            if r["is_correct"]:
                type_accuracy[qtype]["correct"] += r["cnt"]

        return {
            "user": {
                "name": user["name"] if user else "",
                "account": user["account"] if user else "",
                "member_since": user["created_at"] if user else 0,
            },
            "stats": {
                "total_attempts": total_attempts, "total_correct": total_correct,
                "overall_accuracy": round(total_correct / total_attempts, 3) if total_attempts > 0 else 0,
            },
            "type_accuracy": {
                t: {
                    "accuracy": round(d["correct"] / d["total"], 3) if d["total"] > 0 else 0,
                    "total": d["total"], "correct": d["correct"],
                }
                for t, d in type_accuracy.items()
            },
            "weak_concepts": profile.get("weak_concepts", []),
            "strong_concepts": profile.get("strong_concepts", []),
            "recent_practice": [
                {
                    "question_id": r["question_id"], "qtype": r["qtype"],
                    "is_correct": r["is_correct"], "created_at": r["created_at"],
                }
                for r in recent
            ],
        }
