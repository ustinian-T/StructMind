"""SSE 流式工具 —— FastAPI StreamingResponse 封装。"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse


def sse_stream(sync_generator) -> StreamingResponse:
    """将同步生成器包装为 SSE StreamingResponse。

    Usage:
        @router.post("/api/ai/tutor/stream")
        async def tutor_stream(...):
            return sse_stream(socratic_tutor_stream(...))
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        import asyncio

        loop = asyncio.get_event_loop()
        try:
            for item in sync_generator:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True}, ensure_ascii=False)}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Connection": "close",
            "X-Content-Type-Options": "nosniff",
        },
    )
