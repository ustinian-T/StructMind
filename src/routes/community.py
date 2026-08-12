"""社区路由 —— /api/community/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Query

from src.models.schemas import CommunityPostRequest, CommunityReplyRequest
from src.routes.deps import require_auth, make_error_response

router = APIRouter(prefix="/community", tags=["community"])


@router.post("/post")
async def create_post(req: CommunityPostRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        title = req.title.strip()
        content = req.content.strip()
        if not title or not content:
            raise ValueError("标题和内容不能为空。")
        post_id = db.create_post(
            _auth["user_id"], req.question_id, req.bank_id, title, content,
        )
        return {"post_id": post_id}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/posts")
async def get_posts(
    request: Request,
    question_id: int | None = Query(None),
    bank_id: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    try:
        db = request.app.state.db
        posts = db.get_posts(question_id=question_id, bank_id=bank_id, limit=limit, offset=offset)
        return {"posts": posts}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/reply")
async def create_reply(req: CommunityReplyRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        content = req.content.strip()
        if not content:
            raise ValueError("回复内容不能为空。")
        reply_id = db.create_reply(req.post_id, _auth["user_id"], content)
        return {"reply_id": reply_id}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
