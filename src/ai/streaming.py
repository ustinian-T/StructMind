"""SSE 流式工具 —— FastAPI StreamingResponse 封装。"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, AsyncIterator

from fastapi.responses import StreamingResponse


def sse_stream(event_iterator: AsyncIterator[Any]) -> StreamingResponse:
    """Serialize one asynchronous Agent event iterator as SSE.

    Usage:
        @router.post("/api/ai/tutor/stream")
        async def tutor_stream(...):
            return sse_stream(orchestrator.stream(...))
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for item in event_iterator:
                if hasattr(item, "model_dump"):
                    item = item.model_dump(mode="json")
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'protocol': 'structmind.agent.v1', 'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
