"""题库解析验证测试（更新模块路径）。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.parser import load_question_bank, load_assignment_bank
from src.db.database import grade_answer
from src.config import ROOT as CONFIG_ROOT


def find_question(bank, text):
    for question in bank.questions:
        if text in question.stem:
            return question
    raise AssertionError(f"question not found: {text}")


def main():
    bank = load_question_bank()
    assignment = load_assignment_bank()
    assert len(bank.questions) == 323, len(bank.questions)
    assert len(bank.discussions) == 35, len(bank.discussions)

    counts = {}
    for question in bank.questions:
        counts[question.qtype] = counts.get(question.qtype, 0) + 1
    assert counts == {"单选题": 218, "填空题": 68, "多选题": 12, "判断题": 25}, counts

    image_questions = [question for question in bank.questions if question.images]
    assert len(image_questions) == 3, image_questions
    assert any("如图所示的二叉树BT" in question.stem for question in image_questions)

    assert all(question.answer for question in bank.questions)
    assert all(question.id == index for index, question in enumerate(bank.questions, start=1))
    assert all(question.options for question in bank.questions if question.qtype == "判断题")

    repaired = [question for question in bank.questions if question.repaired]
    assert len(repaired) == 5, [(question.id, question.answer) for question in repaired]

    stack_question = find_question(bank, "123按顺序进栈")
    assert grade_answer(stack_question, "312")["is_correct"]

    sparse_question = find_question(bank, "边结点有____个")
    assert grade_answer(sparse_question, "2*e")["is_correct"]
    assert grade_answer(sparse_question, "2e")["is_correct"]

    multi_question = find_question(bank, "以下属于算法特性")
    assert grade_answer(multi_question, ["D", "C", "B", "A"])["is_correct"]

    judgment_question = find_question(bank, "数组可看成线性结构的一种推广")
    assert judgment_question.qtype == "判断题"
    # 答案取决于 DOCX 中记录的数据
    if judgment_question.answer == "错":
        assert grade_answer(judgment_question, "错")["is_correct"]
    else:
        assert grade_answer(judgment_question, "对")["is_correct"]

    # 作业题
    assert len(assignment.questions) == 26, len(assignment.questions)
    assert all(question.answer for question in assignment.questions)

    print("所有解析测试通过 ✓")


if __name__ == "__main__":
    main()
