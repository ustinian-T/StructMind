"""Asynchronous OpenAI-compatible gateway used exclusively by Agent turns."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.ai.client import _get_proxy
from src.ai.providers import ai_api_key, normalize_model, provider_for_model
from src.config import AI_PROVIDERS, AI_TIMEOUT_SECONDS


class NativeToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelStreamEvent(BaseModel):
    type: Literal["delta", "tool_calls", "usage", "done"]
    content: str | None = None
    tool_calls: list[NativeToolCall] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class AsyncModelGateway:
    """Normalize provider streaming chunks into transport-neutral model events."""

    def __init__(self, model: str | None = None, client: AsyncOpenAI | None = None):
        self.model = normalize_model(model)
        self.provider = provider_for_model(self.model)
        if client is not None:
            self._client = client
            return

        api_key = ai_api_key(self.provider)
        if not api_key:
            label = AI_PROVIDERS[self.provider]["label"]
            raise RuntimeError(f"未设置 {label} API Key，AI 功能暂不可用。")
        base_url = AI_PROVIDERS[self.provider]["url"].replace("/chat/completions", "/v1")
        kwargs: dict[str, Any] = {"timeout": AI_TIMEOUT_SECONDS}
        proxy = _get_proxy()
        if proxy:
            kwargs["http_client"] = httpx.AsyncClient(proxy=proxy)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, **kwargs)

    async def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ModelStreamEvent]:
        request: dict[str, Any] = {
            "model": normalize_model(model) if model else self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request.update({"tools": tools, "tool_choice": "auto"})

        try:
            stream = await self._client.chat.completions.create(**request)
        except TypeError:
            # Some OpenAI-compatible providers do not support stream_options.
            request.pop("stream_options", None)
            stream = await self._client.chat.completions.create(**request)

        tool_fragments: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                yield ModelStreamEvent(
                    type="usage",
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = choice.delta
            content = getattr(delta, "content", None)
            if content:
                yield ModelStreamEvent(type="delta", content=content)
            for part in getattr(delta, "tool_calls", None) or []:
                index = int(getattr(part, "index", 0) or 0)
                current = tool_fragments.setdefault(index, {"id": "", "name": "", "arguments": ""})
                current["id"] += getattr(part, "id", None) or ""
                function = getattr(part, "function", None)
                if function is not None:
                    current["name"] += getattr(function, "name", None) or ""
                    current["arguments"] += getattr(function, "arguments", None) or ""

        if tool_fragments:
            calls: list[NativeToolCall] = []
            for index in sorted(tool_fragments):
                item = tool_fragments[index]
                try:
                    arguments = json.loads(item["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {"_invalid_json": item["arguments"]}
                calls.append(NativeToolCall(
                    id=item["id"] or f"tool-{index}",
                    name=item["name"],
                    arguments=arguments,
                ))
            yield ModelStreamEvent(type="tool_calls", tool_calls=calls)
        yield ModelStreamEvent(type="done", finish_reason=finish_reason or "stop")
