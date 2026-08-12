"""共享依赖 —— 数据库、认证、校验、错误处理。

从 __init__.py 分离出来避免循环导入问题。
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Header, Request


# ═══ 数据库 / 题库依赖 ═══


def get_db(request: Request):
    return request.app.state.db


def get_exam_bank(request: Request):
    return request.app.state.exam_bank


def get_assignment_bank(request: Request):
    return request.app.state.assignment_bank


def selected_bank(bank_id: str | None, exam_bank, assignment_bank):
    normalized = (bank_id or "exam").strip()
    if normalized in {"exam", "bank"}:
        return exam_bank
    if normalized == "assignment":
        return assignment_bank
    raise ValueError(f"不支持的题库: {normalized}")


# ═══ 认证依赖 ═══


def parse_auth_header(
    authorization: str | None = None, db=None,
) -> dict[str, Any] | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not db:
        return None
    return db.get_session(token)


async def require_auth(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    db = request.app.state.db
    session = parse_auth_header(authorization=authorization, db=db)
    if not session:
        raise PermissionError("请先登录。")
    if session.get("status") == "pending":
        raise PermissionError("账号尚未通过审批，请等待管理员审核。")
    if session.get("status") == "rejected":
        raise PermissionError("账号注册已被拒绝。")
    return session


async def require_admin(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    session = await require_auth(request, authorization)
    if session.get("role") != "admin":
        raise PermissionError("仅管理员可执行此操作。")
    return session


# ═══ 输入验证 ═══


def validate_account(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) < 2 or len(value) > 32:
        raise ValueError("账号长度需在2-32个字符之间。")
    if not re.match(r"^[a-zA-Z0-9_@.\-]+$", value):
        raise ValueError("账号只能包含字母、数字、下划线、@、点和短横线。")
    return value


def validate_password(value: str) -> str:
    if not value or len(value) < 8 or len(value) > 128:
        raise ValueError("密码长度需在8-128个字符之间。")
    if not re.search(r"[A-Z]", value):
        raise ValueError("密码必须包含至少一个大写字母。")
    if not re.search(r"[a-z]", value):
        raise ValueError("密码必须包含至少一个小写字母。")
    if not re.search(r"[0-9]", value):
        raise ValueError("密码必须包含至少一个数字。")
    return value


def validate_name(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) < 1 or len(value) > 50:
        raise ValueError("姓名长度需在1-50个字符之间。")
    return value


def validate_phone(value: str) -> str:
    value = (value or "").strip()
    if not re.match(r"^\d{11}$", value):
        raise ValueError("请输入正确的11位手机号码。")
    return value


# ═══ 错误映射 ═══


def make_error_response(exc: Exception) -> tuple[int, dict[str, Any]]:
    """将异常映射为 HTTP 状态码 + 错误响应字典。"""
    from src.ai.providers import AIProviderError

    if isinstance(exc, AIProviderError):
        return 502, {"error": str(exc)}
    if isinstance(exc, KeyError):
        return 404, {"error": str(exc)}
    if isinstance(exc, ValueError):
        return 400, {"error": str(exc)}
    if isinstance(exc, PermissionError):
        return 403, {"error": str(exc)}
    return 400, {"error": str(exc)}
