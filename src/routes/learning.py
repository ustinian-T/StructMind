"""学习 + 排行榜路由 —— /api/recommend/*, /api/learning/*, /api/report/*, /api/leaderboard, /api/supplements, /api/discussions"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from src.models.schemas import RecommendRequest, GeneratePlanRequest, ReviewFeedbackRequest
from src.learning.service import LearningLoopService, utc_now
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
        plan_data = generate_learning_plan_data(exam_bank, db, _auth["user_id"])
        db.create_learning_plan(_auth["user_id"], plan_data)
        plan = db.get_learning_plan(_auth["user_id"])
        return {"plan": plan}
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
