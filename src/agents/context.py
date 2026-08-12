"""Trusted context and resource budgets for one Tutor Agent turn."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentBudget(BaseModel):
    """Hard limits applied by the orchestrator, independent of model prompts."""

    model_config = ConfigDict(frozen=True)

    max_tool_rounds: int = Field(default=2, ge=0, le=8)
    max_output_tokens: int = Field(default=1200, ge=32, le=16_384)
    timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    max_history_messages: int = Field(default=12, ge=0, le=100)


class TurnContext(BaseModel):
    """All trusted state needed to execute one tutor turn.

    Identity is intentionally not included in ``model_messages``. It is used by
    the service to authorize tools and persistence, never as prompt content.
    """

    model_config = ConfigDict(frozen=True)

    user_id: int | str
    message: str = Field(min_length=1, max_length=12_000)
    history: list[dict[str, Any]] = Field(default_factory=list)
    question_context: str = Field(default="", max_length=20_000)
    user_profile: dict[str, Any] | None = None
    conversation_id: int | str | None = None
    question_id: int | str | None = None
    mode: Literal["standard", "multi_agent"] = "standard"
    model: str | None = None
    budget: AgentBudget = Field(default_factory=AgentBudget)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be empty")
        return value

    def safe_history(self) -> list[dict[str, str]]:
        """Return only user/assistant text messages within the history budget."""
        safe: list[dict[str, str]] = []
        for item in self.history:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            safe.append({"role": role, "content": content[:12_000]})
        limit = self.budget.max_history_messages
        return safe[-limit:] if limit else []

    def model_messages(self, system_prompt: str) -> list[dict[str, str]]:
        """Build model-visible messages without leaking trusted identity fields."""
        system = system_prompt
        if self.question_context:
            system += f"\n\n## 当前题目上下文\n{self.question_context}"
        messages = [{"role": "system", "content": system}]
        messages.extend(self.safe_history())
        messages.append({"role": "user", "content": self.message})
        return messages
