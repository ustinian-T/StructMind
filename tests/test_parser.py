from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def find_question(bank, text):
    for question in bank.questions:
        if text in question.stem:
            return question
    raise AssertionError(f"question not found: {text}")


def main():
    bank = server.load_question_bank()
    assignment = server.load_assignment_bank()
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
    assert server.grade_answer(stack_question, "312")["is_correct"]

    sparse_question = find_question(bank, "边结点有____个")
    assert server.grade_answer(sparse_question, "2*e")["is_correct"]
    assert server.grade_answer(sparse_question, "2e")["is_correct"]

    multi_question = find_question(bank, "以下属于算法特性")
    assert server.grade_answer(multi_question, ["D", "C", "B", "A"])["is_correct"]

    judgment_question = find_question(bank, "数组可看成线性结构的一种推广")
    assert server.grade_answer(judgment_question, "B")["is_correct"]
    assert server.grade_answer(judgment_question, " B ")["is_correct"]
    assert server.grade_answer(judgment_question, "B. 错")["is_correct"]
    assert server.grade_answer(judgment_question, "错 的")["is_correct"]
    assert not server.grade_answer(judgment_question, "A")["is_correct"]

    zero_score_question = find_question(bank, "具有6个顶点的无向图至少应有____条边")
    assert zero_score_question.score == 0
    assert server.grade_answer(zero_score_question, "5")["is_correct"]

    session = server.create_session(bank, {"mode": "wrong", "question_ids": [3, 1]})
    assert [item["id"] for item in session["questions"]] == [3, 1]
    assert server.normalize_model("deepseek-v4-flash") == "deepseek-v4-flash"
    assert server.ai_choice_text({"delta": {"content": [{"type": "text", "text": "讲解"}]}}) == "讲解"
    assert server.ai_choice_text({"delta": {"reasoning_content": "思考中"}}) == "思考中"

    assignment_counts = {}
    for question in assignment.questions:
        assignment_counts[question.qtype] = assignment_counts.get(question.qtype, 0) + 1
        combined = "\n".join([question.stem, question.answer])
        assert "我的答案：" not in combined
        assert "***：" not in combined
    assert len(assignment.questions) == 26, len(assignment.questions)
    assert assignment_counts == {"简答题": 25, "填空题": 1}, assignment_counts
    assert len([q for q in assignment.questions if q.answer_source == "word_answer"]) == 23
    assert len([q for q in assignment.questions if q.answer_source == "ai_reference"]) == 3
    assert len([q for q in assignment.questions if q.images]) == 2
    assert all(question.answer for question in assignment.questions)

    assignment_session = server.create_session(assignment, {"mode": "sequence", "count": "all"})
    assert assignment_session["bank_id"] == "assignment"
    assert len(assignment_session["questions"]) == 26

    print("parser tests passed")


if __name__ == "__main__":
    main()
