"""作业题 / 讨论题路由 —— /api/assignment/*, /api/discussion/*"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from src.models.schemas import AssignmentGradeRequest, DiscussionGradeRequest
from src.ai.client import AIClient
from src.db.database import public_assignment_question, public_discussion
from src.routes.deps import require_auth, selected_bank, make_error_response

router = APIRouter(tags=["assignment"])


@router.post("/assignment/grade")
async def grade_assignment(req: AssignmentGradeRequest, request: Request):
    try:
        db = request.app.state.db
        assignment_bank = request.app.state.assignment_bank
        question_id = req.question_id or req.assignment_id
        if not question_id:
            raise KeyError("请提供题目ID。")
        question = assignment_bank.by_id.get(question_id)
        if not question:
            raise KeyError("作业题不存在。")
        answer = req.answer.strip()
        if len(answer) < 2:
            raise ValueError("请先写出你的回答。")
        if not question.answer:
            raise ValueError("本题没有可用参考答案。")

        client = AIClient(model=req.model)
        source_label = "Word正确答案" if question.answer_source == "word_answer" else "AI参考答案"

        from src.models.schemas import AssignmentFeedback
        feedback = client.chat_structured(
            [
                {"role": "system", "content": "你是数据结构课程助教。按参考答案给学习建议，不把AI参考答案说成官方答案。只输出JSON。"},
                {"role": "user", "content": json.dumps({
                    "assignment_question": public_assignment_question(question, include_answer=True),
                    "reference_source": source_label,
                    "student_answer": answer,
                }, ensure_ascii=False)},
            ],
            response_model=AssignmentFeedback,
            model=req.model,
            temperature=0.2,
            max_tokens=1500,
        )

        db.record_assignment_feedback(
            question_id, req.model or "default",
            question.answer_source, answer,
            feedback.model_dump(),
        )
        return {
            "question": public_assignment_question(question, include_answer=True),
            "answer_source": question.answer_source,
            "feedback": feedback.model_dump(),
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/discussion/grade")
async def grade_discussion(req: DiscussionGradeRequest, request: Request):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        discussion = exam_bank.discussion_by_id.get(req.discussion_id)
        if not discussion:
            raise KeyError("讨论题不存在。")
        answer = req.answer.strip()
        if len(answer) < 4:
            raise ValueError("请先写出你的回答。")

        client = AIClient(model=req.model)

        from src.models.schemas import DiscussionFeedback
        feedback = client.chat_structured(
            [
                {"role": "system", "content": "你是数据结构课程助教。对学生的讨论题答案给出参考批改而不是绝对判分。只输出JSON。"},
                {"role": "user", "content": json.dumps({
                    "discussion_question": public_discussion(discussion),
                    "student_answer": answer,
                }, ensure_ascii=False)},
            ],
            response_model=DiscussionFeedback,
            model=req.model,
            temperature=0.2,
            max_tokens=1400,
        )

        db.record_discussion_feedback(req.discussion_id, req.model or "default", answer, feedback.model_dump())
        return {"discussion": public_discussion(discussion), "feedback": feedback.model_dump()}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
