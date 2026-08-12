"""管理路由 —— /api/admin/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.models.schemas import ApproveRequest
from src.routes.deps import require_admin, make_error_response

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pending")
async def pending_users(request: Request, _admin=Depends(require_admin)):
    try:
        db = request.app.state.db
        return {"users": db.get_pending_users()}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/users")
async def all_users(request: Request, _admin=Depends(require_admin)):
    try:
        db = request.app.state.db
        return {"users": db.get_all_users()}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/approve")
async def approve(req: ApproveRequest, request: Request, _admin=Depends(require_admin)):
    try:
        db = request.app.state.db
        return {"user": db.approve_user(req.user_id, req.approved)}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
