"""学习 + 排行榜路由 —— /api/recommend/*, /api/learning/*, /api/report/*, /api/leaderboard, /api/supplements, /api/discussions"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from src.models.schemas import (
    RecommendRequest,
    GeneratePlanRequest,
    ReviewFeedbackRequest,
    LearningNoteCreateRequest,
    LearningNoteUpdateRequest,
)
from src.learning.service import LearningLoopService, utc_now
from src.learning.rules import CONCEPT_KEYWORDS
from src.services.recommendation import recommend_questions, generate_learning_plan_data
from src.services.parser import supplements_payload
from src.services.report import generate_learning_report_html
from src.db.database import public_discussion
from src.routes.deps import require_auth, selected_bank, parse_auth_header, make_error_response

router = APIRouter(tags=["learning"])


@router.get("/learning/events/{event_id}")
async def learning_event(event_id: str, request: Request, _auth=Depends(require_auth)):
    try:
        return {"event": request.app.state.db.get_learning_event(_auth["user_id"], event_id)}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/learning/reviews")
async def due_reviews(request: Request, at: str | None = None, _auth=Depends(require_auth)):
    try:
        evaluated_at = at or utc_now()
        return {"reviews": request.app.state.db.get_due_reviews(_auth["user_id"], evaluated_at),
                "evaluated_at": evaluated_at}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/learning/reviews/feedback")
async def review_feedback(req: ReviewFeedbackRequest, request: Request, _auth=Depends(require_auth)):
    try:
        service = LearningLoopService(request.app.state.db, request.app.state.exam_bank)
        result = service.record_review_feedback(
            user_id=_auth["user_id"], concept=req.concept.strip(), feedback=req.feedback,
            learning_event_id=req.learning_event_id,
        )
        return {"review_feedback": result}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/recommend/questions")
async def recommend(req: RecommendRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        profile = db.get_user_profile(_auth["user_id"])
        bank = selected_bank(req.bank_id, exam_bank, request.app.state.assignment_bank)
        return recommend_questions(bank, db, profile, _auth["user_id"], req.model_dump())
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/learning/generate-plan")
async def generate_plan(_req: GeneratePlanRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        plan_data = generate_learning_plan_data(
            exam_bank, db, _auth["user_id"], exam_date=_req.exam_date,
            daily_minutes=_req.daily_minutes, timezone=_req.timezone,
            evaluated_at=_req.evaluated_at or utc_now(),
        )
        db.create_learning_plan(_auth["user_id"], plan_data)
        plan = db.get_learning_plan(_auth["user_id"])
        return {"plan": plan}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/learning/plans")
async def plan_history(request: Request, _auth=Depends(require_auth)):
    try:
        return {"plans": request.app.state.db.get_learning_plan_history(_auth["user_id"])}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/learning/conversations/{conversation_id}/summary")
async def refresh_summary(conversation_id: int, request: Request, _auth=Depends(require_auth)):
    try:
        known = [name for name, _keywords in CONCEPT_KEYWORDS]
        result = request.app.state.db.refresh_conversation_summary(
            _auth["user_id"], conversation_id, known,
        )
        return {"summary": result}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/learning/notes")
async def create_note(req: LearningNoteCreateRequest, request: Request, _auth=Depends(require_auth)):
    try:
        note = request.app.state.db.create_learning_note(
            _auth["user_id"], req.title.strip(), req.user_content, req.tags, req.concept,
        )
        return {"note": note}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/learning/notes")
async def list_notes(
    request: Request, archived: bool = False, source_type: str | None = None,
    concept: str | None = None, _auth=Depends(require_auth),
):
    try:
        return {"notes": request.app.state.db.list_learning_notes(
            _auth["user_id"], archived=archived, source_type=source_type, concept=concept,
        )}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.patch("/learning/notes/{note_id}")
async def update_note(
    note_id: str, req: LearningNoteUpdateRequest, request: Request, _auth=Depends(require_auth),
):
    try:
        note = request.app.state.db.update_learning_note(
            _auth["user_id"], note_id, req.model_dump(exclude_unset=True),
        )
        return {"note": note}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/learning/plan")
async def get_plan(request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        plan = db.get_learning_plan(_auth["user_id"])
        return {"plan": plan}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/report/pdf")
async def get_report(request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        report_data = db.get_learning_report_data(_auth["user_id"])
        html = generate_learning_report_html(report_data)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/leaderboard")
async def leaderboard(request: Request, period: str = Query("week")):
    try:
        db = request.app.state.db
        board = db.get_leaderboard(period)
        return {"leaderboard": board, "period": period}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/supplements")
async def supplements(request: Request):
    try:
        return supplements_payload(request.app.state.exam_bank, request.app.state.assignment_bank)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/discussions")
async def discussions(request: Request):
    try:
        exam_bank = request.app.state.exam_bank
        return {"discussions": [public_discussion(item) for item in exam_bank.discussions]}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
