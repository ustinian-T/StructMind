"""Versioned transport-neutral event protocol for Tutor Agent turns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AGENT_PROTOCOL = "structmind.agent.v1"
AgentEventType = Literal[
    "meta",
    "route",
    "delta",
    "tool_start",
    "tool_result",
    "usage",
    "done",
    "error",
]


class AgentEvent(BaseModel):
    """One event envelope shared by REST, SSE, WebSocket and uniCloud."""

    model_config = ConfigDict(extra="forbid", exclude_none=True)

    protocol: Literal["structmind.agent.v1"] = AGENT_PROTOCOL
    type: AgentEventType
    run_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content: str | None = None
    mode: str | None = None
    model: str | None = None
    intent: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = None
    code: str | None = None
    message: str | None = None
    conversation_id: int | str | None = None

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Serialize a compact wire envelope by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(*args, **kwargs)

    @model_validator(mode="after")
    def _validate_type_payload(self) -> "AgentEvent":
        if self.type == "delta" and self.content is None:
            raise ValueError("delta event requires content")
        if self.type in {"tool_start", "tool_result"}:
            if not self.tool_call_id or not self.tool_name:
                raise ValueError("tool events require tool_call_id and tool_name")
        if self.type == "tool_start" and self.arguments is None:
            raise ValueError("tool_start requires arguments")
        if self.type == "tool_result" and self.result is None:
            raise ValueError("tool_result requires result")
        if self.type == "error" and not self.message:
            raise ValueError("error event requires message")
        return self


class EventFactory:
    """Create monotonic events for a single run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._sequence = 0

    def create(self, event_type: AgentEventType, **payload: Any) -> AgentEvent:
        self._sequence += 1
        return AgentEvent(
            type=event_type,
            run_id=self.run_id,
            sequence=self._sequence,
            **payload,
        )
