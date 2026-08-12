"""系统配置路由 —— /api/config, /api/stats, /api/bank/*"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from src.ai.providers import config_payload, update_runtime_config
from src.services.parser import stats_payload
from src.models.schemas import ConfigUpdateRequest, BankUploadRequest, BankGetRequest
from src.routes.deps import require_auth, parse_auth_header, make_error_response

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config():
    return config_payload()


@router.post("/config")
async def update_config(req: ConfigUpdateRequest):
    try:
        return update_runtime_config(req.model_dump(exclude_none=True))
    except Exception as exc:
        status, body = make_error_response(exc)
        from fastapi.responses import JSONResponse
        return JSONResponse(body, status_code=status)


@router.get("/stats")
async def get_stats(request: Request):
    try:
        exam_bank = request.app.state.exam_bank
        assignment_bank = request.app.state.assignment_bank
        db = request.app.state.db
        config = config_payload()
        return stats_payload(exam_bank, assignment_bank, db, config)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


# ── 自定义题库 ──


@router.get("/bank/list")
async def bank_list(request: Request):
    try:
        db = request.app.state.db
        session = parse_auth_header(request.headers.get("Authorization"), db=db)
        user_id = session["user_id"] if session else 0
        user_banks = db.list_custom_banks(user_id) if user_id > 0 else []
        public_banks = db.list_public_banks()
        seen = {b["id"] for b in user_banks}
        all_banks = list(user_banks)
        for b in public_banks:
            if b["id"] not in seen:
                all_banks.append(b)
                seen.add(b["id"])
        return {"banks": all_banks}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/bank/upload")
async def bank_upload(req: BankUploadRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        name = req.name.strip()
        if not name or len(name) > 100:
            raise ValueError("题库名称长度需在1-100个字符之间。")
        if not isinstance(req.questions, list):
            raise ValueError("questions 必须是数组。")
        bank_id = db.create_custom_bank(
            name, _auth["user_id"],
            json.dumps(req.questions, ensure_ascii=False),
        )
        return {"bank_id": bank_id, "name": name}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/bank/get")
async def bank_get(req: BankGetRequest, request: Request):
    try:
        db = request.app.state.db
        bank = db.get_custom_bank(req.bank_id)
        if not bank:
            raise KeyError("题库不存在。")
        return {"bank": bank}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
