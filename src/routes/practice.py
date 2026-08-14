"""练习路由 —— /api/session, /api/answer, /api/questions, /api/wrong, /api/profile"""

from __future__ import annotations

import json
import random
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.models.schemas import SessionRequest, AnswerRequest, ConceptUpdateRequest
from src.db.database import public_bank_question, grade_answer, extract_concepts_from_stem
from src.learning.service import LearningLoopService
from src.routes.deps import (
    get_db,
    get_exam_bank,
    get_assignment_bank,
    selected_bank,
    require_auth,
    parse_auth_header,
    make_error_response,
)

router = APIRouter(tags=["practice"])


@router.post("/session")
async def create_session_view(req: SessionRequest, request: Request):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        assignment_bank = request.app.state.assignment_bank

        bank_id = req.bank_id
        custom_bank_id = None
        try:
            custom_bank_id = int(bank_id) if bank_id and str(bank_id).isdigit() else None
        except (ValueError, TypeError):
            pass

        if custom_bank_id:
            custom_bank = db.get_custom_bank(custom_bank_id)
            if custom_bank:
                questions_data = json.loads(custom_bank["questions_json"])
                return {
                    "session_id": str(uuid.uuid4()),
                    "bank_id": f"custom_{custom_bank_id}",
                    "mode": req.mode,
                    "total_available": len(questions_data),
                    "count": len(questions_data),
                    "questions": questions_data,
                }
            raise KeyError("自定义题库不存在。")

        bank = selected_bank(req.bank_id, exam_bank, assignment_bank)
        mode = req.mode or "sequence"

        if req.question_ids:
            id_order = [int(item) for item in req.question_ids]
            questions = [bank.by_id[item] for item in id_order if item in bank.by_id]
        else:
            questions = list(bank.questions)
            types = set(req.types or [])
            chapters = set(req.chapters or [])
            if types:
                questions = [q for q in questions if q.qtype in types]
            if chapters:
                questions = [q for q in questions if q.chapter in chapters]

        count = len(questions)
        if req.count not in (None, "", 0, "0", "all"):
            count = max(1, min(int(req.count), len(questions)))

        if mode == "random":
            selected = random.sample(questions, count) if count else []
        else:
            selected = questions[:count]

        return {
            "session_id": str(uuid.uuid4()),
            "bank_id": bank.bank_id,
            "mode": mode,
            "total_available": len(questions),
            "count": len(selected),
            "questions": [public_bank_question(q) for q in selected],
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/answer")
async def submit_answer(req: AnswerRequest, request: Request):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        assignment_bank = request.app.state.assignment_bank
        bank = selected_bank(req.bank_id, exam_bank, assignment_bank)
        question = bank.by_id.get(req.question_id)
        if not question:
            raise KeyError("题目不存在。")
        if hasattr(question, "answer_source") and question.qtype == "简答题":
            raise ValueError("简答作业题请使用 AI 参考批改。")
        result = grade_answer(question, req.answer)
        user_id = 0
        session = parse_auth_header(request.headers.get("Authorization"), db=db)
        if session:
            user_id = session["user_id"]
        if user_id > 0:
            if not (req.attempt_token or "").strip():
                raise ValueError("attempt_token 不能为空。")
            result = LearningLoopService(db, bank).submit_answer(
                user_id=user_id,
                question=question,
                answer=req.answer,
                grading=result,
                attempt_token=req.attempt_token,
                session_id=req.session_id,
                time_spent_seconds=req.time_spent_seconds,
            )
        else:
            chapter = getattr(question, "chapter", "") or ""
            db.record_attempt(
                question.id, bank.bank_id, question.qtype,
                req.answer, question.answer, result["is_correct"],
                user_id=user_id, chapter=chapter,
            )
        result["question"] = public_bank_question(question, include_answer=True)
        return result
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/questions")
async def list_questions(request: Request, bank_id: str = "exam"):
    try:
        bank = selected_bank(bank_id, request.app.state.exam_bank, request.app.state.assignment_bank)
        return {
            "bank_id": bank.bank_id,
            "questions": [public_bank_question(item) for item in bank.questions],
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/wrong")
async def wrong_questions(request: Request):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        session = parse_auth_header(request.headers.get("Authorization"), db=db)
        if session:
            return {"items": db.wrong_attempts(exam_bank, user_id=int(session["user_id"]))}
        return {"items": []}
    except Exception:
        return {"items": []}


@router.get("/profile")
async def get_profile(request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        session = _auth
        profile = db.get_user_profile(session["user_id"])
        if not profile:
            profile = db.update_user_profile(session["user_id"])
        return {"profile": profile, "user": session}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/concept/update")
async def update_concept(req: ConceptUpdateRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        concept = req.concept.strip()
        if not concept:
            raise ValueError("概念名称不能为空。")
        mastery = db.update_concept_mastery(_auth["user_id"], concept, req.is_correct)
        return {"mastery": mastery}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
