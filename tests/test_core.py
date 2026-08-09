"""
StructMind 核心功能单元测试
运行: py -m pytest tests/test_core.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import json
import pytest


# ═══ 密码哈希测试 ═══
from server import hash_password, verify_password

def test_hash_password_returns_salt_and_hash():
    result = hash_password("TestPass123")
    assert "$" in result
    salt, h = result.split("$", 1)
    assert len(salt) == 32  # 16 bytes hex = 32 chars
    assert len(h) == 64     # SHA256 hex = 64 chars


def test_verify_password_correct():
    stored = hash_password("MySecret1")
    assert verify_password("MySecret1", stored) is True


def test_verify_password_incorrect():
    stored = hash_password("MySecret1")
    assert verify_password("wrong", stored) is False


def test_verify_password_empty():
    stored = hash_password("")
    assert verify_password("", stored) is True


# ═══ 输入验证测试 ═══
from server import validate_account, validate_password, validate_name, validate_phone

def test_validate_account_valid():
    assert validate_account("test_user") == "test_user"
    assert validate_account("a@b.com") == "a@b.com"
    assert validate_account("abc") == "abc"


def test_validate_account_too_short():
    with pytest.raises(ValueError, match="2-32"):
        validate_account("a")


def test_validate_account_invalid_chars():
    with pytest.raises(ValueError, match="字母、数字"):
        validate_account("test user")


def test_validate_password_valid():
    assert validate_password("123456") == "123456"
    assert validate_password("a" * 100) == "a" * 100


def test_validate_password_too_short():
    with pytest.raises(ValueError, match="6-128"):
        validate_password("12345")


def test_validate_phone_valid():
    assert validate_phone("13800138000") == "13800138000"


def test_validate_phone_invalid():
    with pytest.raises(ValueError, match="11位"):
        validate_phone("12345")


# ═══ 答案批改测试 ═══
from server import (
    normalize_choice_answer, normalize_multi_answer,
    normalize_fill, fill_candidates, grade_answer,
    ObjectiveQuestion,
)

@pytest.fixture
def single_choice_q():
    return ObjectiveQuestion(
        id=1, source_order=1, source_num="1", qtype="单选题",
        chapter="第一章", stem="测试题", options=[
            {"key": "A", "text": "选项A"},
            {"key": "B", "text": "选项B"},
            {"key": "C", "text": "选项C"},
            {"key": "D", "text": "选项D"},
        ], answer="B", raw_correct="B", score=2,
    )


@pytest.fixture
def judge_q():
    return ObjectiveQuestion(
        id=2, source_order=2, source_num="2", qtype="判断题",
        chapter="第一章", stem="判断题测试",
        options=[{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
        answer="A", raw_correct="A", score=1,
    )


@pytest.fixture
def multi_choice_q():
    return ObjectiveQuestion(
        id=3, source_order=3, source_num="3", qtype="多选题",
        chapter="第二章", stem="多选题测试", options=[
            {"key": "A", "text": "A"}, {"key": "B", "text": "B"},
            {"key": "C", "text": "C"}, {"key": "D", "text": "D"},
        ], answer="ABC", raw_correct="ABC", score=3,
    )


@pytest.fixture
def fill_q():
    return ObjectiveQuestion(
        id=4, source_order=4, source_num="4", qtype="填空题",
        chapter="第三章", stem="填空测试", options=[],
        answer="n(n+1)/2", raw_correct="n(n+1)/2", score=2,
    )


def test_normalize_choice_answer_simple():
    assert normalize_choice_answer("B") == "B"
    assert normalize_choice_answer("  b  ") == "B"


def test_normalize_choice_answer_chinese_true():
    assert normalize_choice_answer("对") == "A"
    assert normalize_choice_answer("正确") == "A"
    assert normalize_choice_answer("是") == "A"


def test_normalize_choice_answer_chinese_false():
    assert normalize_choice_answer("错") == "B"
    assert normalize_choice_answer("错误") == "B"
    assert normalize_choice_answer("否") == "B"


def test_normalize_multi_answer():
    assert normalize_multi_answer(["B", "A", "C"]) == "ABC"
    assert normalize_multi_answer("CAB") == "ABC"


def test_normalize_fill():
    assert normalize_fill("n(n+1)/2") == "n(n+1)/2"
    assert normalize_fill("  N(N+1)/2  ") == "n(n+1)/2"


def test_grade_single_choice_correct(single_choice_q):
    result = grade_answer(single_choice_q, "B")
    assert result["is_correct"] is True


def test_grade_single_choice_wrong(single_choice_q):
    result = grade_answer(single_choice_q, "A")
    assert result["is_correct"] is False


def test_grade_judge_correct(judge_q):
    result = grade_answer(judge_q, "对")
    assert result["is_correct"] is True


def test_grade_judge_chinese_false(judge_q):
    result = grade_answer(judge_q, "错")
    assert result["is_correct"] is False


def test_grade_multi_choice_correct(multi_choice_q):
    result = grade_answer(multi_choice_q, ["A", "C", "B"])
    assert result["is_correct"] is True


def test_grade_multi_choice_partial(multi_choice_q):
    result = grade_answer(multi_choice_q, ["A", "B"])
    assert result["is_correct"] is False


def test_grade_fill_exact(fill_q):
    result = grade_answer(fill_q, "n(n+1)/2")
    assert result["is_correct"] is True


def test_grade_fill_case_insensitive(fill_q):
    result = grade_answer(fill_q, "N(N+1)/2")
    assert result["is_correct"] is True


# ═══ 文本哈希测试 ═══
from server import text_hash

def test_text_hash_deterministic():
    h1 = text_hash("二叉树遍历")
    h2 = text_hash("二叉树遍历")
    assert h1 == h2


def test_text_hash_different_content():
    h1 = text_hash("二叉树")
    h2 = text_hash("哈希表")
    assert h1 != h2


def test_text_hash_ignores_punctuation():
    h1 = text_hash("数据，结构；练习。")
    h2 = text_hash("数据结构练习")
    assert h1 == h2


# ═══ 推荐算法测试 ═══
from server import recommend_questions, QuestionBank, PracticeDatabase

def test_recommend_questions_returns_correct_count():
    """测试推荐算法返回正确数量的题目"""
    # 这个测试需要实际的题库，使用集成测试方式
    pass  # 需要数据库环境，在集成测试中覆盖


# ═══ Token生成测试 ═══
from server import generate_token

def test_generate_token_length():
    token = generate_token()
    assert len(token) >= 32


def test_generate_token_unique():
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100


# ═══ 数据库测试 ═══
import tempfile
from server import PracticeDatabase, DB_PATH

@pytest.fixture
def temp_db():
    """创建临时数据库"""
    db_path = tempfile.mktemp(suffix='.sqlite3')
    db = PracticeDatabase(db_path)
    yield db
    # 清理
    import os
    try:
        os.remove(db_path)
    except OSError:
        pass


def test_db_init_creates_tables(temp_db):
    """测试数据库初始化创建所有表"""
    with temp_db.connect() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}
        expected = {"attempts", "ai_questions", "discussion_feedback",
                    "assignment_feedback", "users", "sessions",
                    "user_profile", "ai_conversations", "generated_questions"}
        assert expected.issubset(table_names)


def test_user_registration_flow(temp_db):
    """测试完整用户注册流程"""
    # 注册
    user = temp_db.create_user("testuser", "Pass123", "测试", "13800138000")
    assert user["account"] == "testuser"
    assert user["status"] == "pending"

    # 重复注册
    with pytest.raises(ValueError, match="已被注册"):
        temp_db.create_user("testuser", "Pass123", "测试2", "13800138001")

    # 登录（待审批）
    result = temp_db.authenticate("testuser", "Pass123")
    assert result is not None
    assert result["status"] == "pending"

    # 错误密码
    result = temp_db.authenticate("testuser", "wrong")
    assert result is None


def test_admin_approval_flow(temp_db):
    """测试管理员审批流程"""
    # 注册用户
    user = temp_db.create_user("student1", "Pass123", "学生", "13800138000")
    assert user["status"] == "pending"

    # 审批通过
    approved = temp_db.approve_user(user["id"], True)
    assert approved["status"] == "approved"

    # 审批拒绝
    user2 = temp_db.create_user("student2", "Pass123", "学生2", "13800138001")
    rejected = temp_db.approve_user(user2["id"], False)
    assert rejected["status"] == "rejected"


def test_session_lifecycle(temp_db):
    """测试会话生命周期"""
    user = temp_db.create_user("sessuser", "Pass123", "会话测试", "13800138000")
    temp_db.approve_user(user["id"], True)

    token = temp_db.create_session(user["id"])
    assert len(token) >= 32

    session = temp_db.get_session(token)
    assert session is not None
    assert session["user_id"] == user["id"]

    temp_db.delete_session(token)
    assert temp_db.get_session(token) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
