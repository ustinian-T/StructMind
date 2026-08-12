"""认证路由 —— /api/auth/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from src.models.schemas import LoginRequest, RegisterRequest
from src.config import ADMIN_ACCOUNT
from src.routes.deps import (
    get_db,
    require_auth,
    validate_account,
    validate_password,
    validate_name,
    validate_phone,
    make_error_response,
    parse_auth_header,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    try:
        account = validate_account(req.account)
        if account == ADMIN_ACCOUNT:
            raise PermissionError("该账号为系统保留管理员账号，不能公开注册。")
        password = validate_password(req.password)
        name = validate_name(req.name)
        phone = validate_phone(req.phone)
        db = request.app.state.db
        return db.create_user(account, password, name, phone)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    try:
        account = validate_account(req.account)
        password = req.password
        if not password:
            raise ValueError("密码不能为空。")
        db = request.app.state.db
        user = db.authenticate(account, password)
        if not user:
            raise ValueError("账号或密码错误。")
        if user["status"] == "pending":
            raise ValueError("账号正在等待管理员审批，请耐心等候。")
        if user["status"] == "rejected":
            raise ValueError("账号注册已被拒绝。")
        token = db.create_session(user["id"])
        return {"token": token, "user": user}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/logout")
async def logout(request: Request, authorization: str | None = Header(None)):
    try:
        db = request.app.state.db
        if authorization and authorization.startswith("Bearer "):
            db.delete_session(authorization[7:].strip())
        return {"ok": True}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.get("/me")
async def me(session: dict = Depends(require_auth)):
    try:
        return {"user": session}
    except Exception as exc:
        status, body = make_error_response(exc)
        from fastapi.responses import JSONResponse
        return JSONResponse(body, status_code=status)
