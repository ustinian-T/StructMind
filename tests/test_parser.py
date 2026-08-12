"""Word 题库解析与源答案真实性测试。"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.database import grade_answer
from src.services.parser import load_assignment_bank, load_question_bank


@pytest.fixture(scope="module")
def banks():
    return load_question_bank(), load_assignment_bank()


def find_question(bank, text):
    for question in bank.questions:
        if text in question.stem:
            return question
    raise AssertionError(f"question not found: {text}")


def test_exam_bank_counts_and_ids_match_source(banks):
    bank, _assignment = banks
    assert len(bank.questions) == 323
    assert len(bank.discussions) == 35

    counts = {}
    for question in bank.questions:
        counts[question.qtype] = counts.get(question.qtype, 0) + 1
    assert counts == {"单选题": 218, "填空题": 68, "多选题": 12, "判断题": 25}
    assert all(question.answer for question in bank.questions)
    assert all(question.id == index for index, question in enumerate(bank.questions, start=1))
    assert all(question.options for question in bank.questions if question.qtype == "判断题")


def test_exam_bank_images_and_explicit_repairs_are_preserved(banks):
    bank, _assignment = banks
    image_questions = [question for question in bank.questions if question.images]
    repaired = [question for question in bank.questions if question.repaired]

    assert len(image_questions) == 3
    assert any("如图所示的二叉树BT" in question.stem for question in image_questions)
    assert len(repaired) == 5


def test_source_answer_variants_are_graded_equivalently(banks):
    bank, _assignment = banks
    stack_question = find_question(bank, "123按顺序进栈")
    sparse_question = find_question(bank, "边结点有____个")
    multi_question = find_question(bank, "以下属于算法特性")

    assert grade_answer(stack_question, "312")["is_correct"]
    assert grade_answer(sparse_question, "2*e")["is_correct"]
    assert grade_answer(sparse_question, "2e")["is_correct"]
    assert grade_answer(multi_question, ["D", "C", "B", "A"])["is_correct"]


def test_judgment_answer_uses_the_docx_source_value(banks):
    bank, _assignment = banks
    question = find_question(bank, "数组可看成线性结构的一种推广")

    assert question.qtype == "判断题"
    expected = "错" if question.answer == "错" else "对"
    assert grade_answer(question, expected)["is_correct"]


def test_assignment_bank_answers_are_complete(banks):
    _bank, assignment = banks
    assert len(assignment.questions) == 26
    assert all(question.answer for question in assignment.questions)
