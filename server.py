"""StructMind — FastAPI 入口。

启动方式:
    python server.py
    uvicorn server:app --host 127.0.0.1 --port 8765 --reload

OpenAPI 文档:
    http://localhost:8765/docs
"""

from __future__ import annotations

import json
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from src.config import (
    ROOT,
    WEB_DIR,
    PUBLIC_DIR,
    RUNTIME_DIR,
    ASSET_DIR,
    DB_PATH,
    ADMIN_ACCOUNT,
    ADMIN_PASSWORD,
)
from src.ai.providers import AIProviderError
from src.ai.gateway import close_shared_http_client
from src.db.database import PracticeDatabase
from src.services.parser import load_question_bank, load_assignment_bank
from src.routes import api_router
from src.routes.ai import websocket_router


def bootstrap_admin(db: PracticeDatabase) -> bool:
    """Create or repair the configured administrator only with an explicit secret."""
    if not ADMIN_PASSWORD:
        return False
    db.ensure_admin(
        ADMIN_ACCOUNT,
        ADMIN_PASSWORD,
        "谭书宏",
        "13800000000",
    )
    return True


# ── 应用生命周期 ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时加载和清理资源。"""
    # 启动
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    print("载入期末考试题库...")
    exam_bank = load_question_bank()
    print(f"  → {len(exam_bank.questions)} 道客观题, {len(exam_bank.discussions)} 道讨论题")
    print("载入作业题库...")
    assignment_bank = load_assignment_bank()
    print(f"  → {len(assignment_bank.questions)} 道作业题")

    print("初始化数据库...")
    db = PracticeDatabase(DB_PATH)

    # 仅使用显式配置的密码创建或轮换管理员，永不使用内置默认密码。
    if bootstrap_admin(db):
        print(f"管理员账号已就绪: {ADMIN_ACCOUNT}")
    else:
        print("未设置 SM_ADMIN_PASSWORD，已跳过管理员自动创建/密码轮换。")

    app.state.exam_bank = exam_bank
    app.state.assignment_bank = assignment_bank
    app.state.db = db

    yield

    # 关闭：释放共享 httpx 客户端，避免进程退出时连接句柄泄漏。
    await close_shared_http_client()


# ── FastAPI 应用 ──

app = FastAPI(
    title="StructMind API",
    description="数据结构 AI 智练中心",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS
allowed_origins_env = os.environ.get("SM_ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    allow_credentials = True
else:
    allowed_origins = ["*"]
    allow_credentials = False
    print("CORS: SM_ALLOWED_ORIGINS not set, using wildcard with credentials disabled.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=allow_credentials,
)


# ── 异常处理（FastAPI 原生方式） ──


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={"error": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    return JSONResponse(status_code=404, content={"error": str(exc)})


@app.exception_handler(AIProviderError)
async def ai_error_handler(request: Request, exc: AIProviderError):
    return JSONResponse(status_code=502, content={"error": str(exc)})


# 辅助：为路由中的 try/except 提供简化的错误响应
@app.middleware("http")
async def attach_state_helpers(request: Request, call_next):
    """为 request.app.state 附加工具方法。"""
    def _json_response(body: dict, status: int = 200):
        return JSONResponse(content=body, status_code=status)
    request.app.state._json_response = _json_response
    response = await call_next(request)
    return response


# ── API 路由 ──

app.include_router(api_router)
app.include_router(websocket_router)


# ── 静态文件与 SPA ──


@app.get("/assets/{bank_id}/{filename}")
async def serve_asset(bank_id: str, filename: str):
    """安全地提供运行时资源文件。"""
    relative = Path(f"{bank_id}/{filename}")
    if relative.is_absolute() or ".." in relative.parts:
        return Response(status_code=404)
    real_path = (ASSET_DIR / relative).resolve()
    if not str(real_path).startswith(str(ASSET_DIR.resolve())):
        return Response(status_code=403)
    if not real_path.exists() or not real_path.is_file():
        return Response(status_code=404)
    data = real_path.read_bytes()
    content_type = mimetypes.guess_type(str(real_path))[0] or "application/octet-stream"
    return Response(content=data, media_type=content_type)


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """SPA fallback —— 非 API 路径返回前端 index.html。"""
    # API 路径已由路由器处理，这里处理静态文件
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "接口不存在。"})

    clean = full_path.lstrip("/")
    if ".." in clean or clean.startswith("/"):
        return Response(status_code=403)

    for base_dir in (WEB_DIR, PUBLIC_DIR):
        file_path = base_dir / (clean or "index.html")
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(base_dir.resolve())):
                return Response(status_code=403)
            file_path = resolved
        except (ValueError, OSError):
            continue

        if file_path.exists() and file_path.is_file():
            data = file_path.read_bytes()
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            return Response(content=data, media_type=content_type)

    # 最终 fallback 到 index.html（SPA 路由）
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return Response(content=index_path.read_bytes(), media_type="text/html")

    return JSONResponse(status_code=404, content={"error": "页面不存在。"})


# ── 启动 ──

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SM_HOST", "127.0.0.1")
    port = int(os.environ.get("SM_PORT", "8765"))
    ssl_cert = os.environ.get("SM_SSL_CERT")
    ssl_key = os.environ.get("SM_SSL_KEY")

    uvicorn_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "log_level": "info",
    }
    if ssl_cert and ssl_key and os.path.isfile(ssl_cert) and os.path.isfile(ssl_key):
        uvicorn_kwargs["ssl_certfile"] = ssl_cert
        uvicorn_kwargs["ssl_keyfile"] = ssl_key
        print(f"HTTPS 模式已启用")

    print(f"StructMind 服务地址: {'https' if 'ssl_certfile' in uvicorn_kwargs else 'http'}://{host}:{port}")
    print(f"API 文档: http://{host}:{port}/docs")
    uvicorn.run("server:app", **uvicorn_kwargs)
