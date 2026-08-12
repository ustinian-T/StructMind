"""阶段 0 Agent 工具隔离、Provider 与 AI 出题回归测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.agents.generator import generate_ai_question
from src.ai.client import get_ai_client
from src.db.database import PracticeDatabase, text_hash
from src.models import ObjectiveQuestion
from src.models.schemas import GeneratedQuestion, VerificationResult
from src.tools.registry import ToolRegistry, get_tool_definitions


class SingleQuestionBank:
    def __init__(self):
        question = ObjectiveQuestion(
            id=1,
            source_order=1,
            source_num="1",
            qtype="单选题",
            chapter="栈和队列",
            stem="下列哪一种数据结构遵循先进后出原则？",
            options=[
                {"key": "A", "text": "队列"},
                {"key": "B", "text": "栈"},
                {"key": "C", "text": "图"},
                {"key": "D", "text": "散列表"},
            ],
            answer="B",
            raw_correct="B",
            score=2,
        )
        self.questions = [question]
        self.by_id = {question.id: question}


def test_student_profile_tool_is_bound_to_authenticated_user(tmp_path: Path):
    db = PracticeDatabase(tmp_path / "tools.sqlite3")
    current = db.create_user("current", "StudentPass123", "当前用户", "13800138000")
    other = db.create_user("other", "StudentPass123", "其他用户", "13800138001")
    db.update_user_profile(current["id"])
    db.update_user_profile(other["id"])
    registry = ToolRegistry(SingleQuestionBank(), db, current["id"])

    result = registry.execute("get_student_profile", {"user_id": other["id"]})

    assert result["success"] is True
    assert result["data"]["profile"]["user_id"] == current["id"]


def test_student_profile_tool_does_not_expose_user_id_parameter():
    profile_tool = next(
        item for item in get_tool_definitions()
        if item["function"]["name"] == "get_student_profile"
    )

    assert profile_tool["function"]["parameters"]["properties"] == {}


def test_provider_factory_resolves_named_provider(monkeypatch):
    created_models = []

    class FakeAIClient:
        def __init__(self, model):
            created_models.append(model)
            self.model = model

    monkeypatch.setattr("src.ai.client.AIClient", FakeAIClient)

    client = get_ai_client("zhipu")

    assert client.model == "glm-5.1"
    assert created_models == ["glm-5.1"]


def test_ai_question_schema_stores_stem_hash(tmp_path: Path):
    db = PracticeDatabase(tmp_path / "questions.sqlite3")
    item = {
        "qtype": "单选题",
        "stem": "在循环队列中，判断队列为空的条件是什么？",
        "options": [
            {"key": "A", "text": "front == rear"},
            {"key": "B", "text": "front != rear"},
        ],
        "answer": "A",
        "analysis": "队空时两个指针相等。",
    }

    db.record_ai_question(item, "glm-5.1", 1)

    assert text_hash(item["stem"]) in db.get_all_question_stems_and_hashes()


def test_legacy_ai_question_table_is_migrated_with_stem_hash(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE ai_questions (
                id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                source_question_id INTEGER NOT NULL,
                qtype TEXT NOT NULL,
                stem TEXT NOT NULL,
                options_json TEXT NOT NULL,
                answer TEXT NOT NULL,
                analysis TEXT NOT NULL,
                created_at REAL NOT NULL,
                user_id INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            """INSERT INTO ai_questions
               (id, model, source_question_id, qtype, stem, options_json,
                answer, analysis, created_at, user_id)
               VALUES ('legacy', 'glm-5.1', 1, '填空题', '栈的修改原则是____。',
                       '[]', '后进先出', '基础概念', 1, 0)"""
        )

    db = PracticeDatabase(path)

    assert text_hash("栈的修改原则是____。") in db.get_all_question_stems_and_hashes()


def test_ai_question_generation_pipeline_completes_and_persists(tmp_path: Path):
    db = PracticeDatabase(tmp_path / "generation.sqlite3")
    bank = SingleQuestionBank()

    class FakeClient:
        def chat_structured(self, _messages, response_model, **_kwargs):
            if response_model is GeneratedQuestion:
                return GeneratedQuestion(
                    qtype="单选题",
                    stem="若元素依次入栈 1、2、3，首先出栈的元素可能是哪一个？",
                    options=[
                        {"key": "A", "text": "只能是1"},
                        {"key": "B", "text": "只能是2"},
                        {"key": "C", "text": "1、2、3均可能"},
                        {"key": "D", "text": "都不可能"},
                    ],
                    answer="C",
                    analysis="在不同入栈时机执行出栈，三者均可先出栈。",
                )
            if response_model is VerificationResult:
                return VerificationResult(valid=True, answer="C", reason="答案一致")
            raise AssertionError(f"unexpected response model: {response_model}")

    result = generate_ai_question(
        FakeClient(),
        bank,
        db,
        {"model": "glm-5.1", "qtype": "单选题", "source_question_id": 1},
    )

    saved = db.get_ai_question(result["id"])
    assert saved is not None
    assert saved["stem"] == result["question"]["stem"]
    assert text_hash(saved["stem"]) in db.get_all_question_stems_and_hashes()
