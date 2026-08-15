"""Asynchronous OpenAI-compatible gateway used exclusively by Agent turns."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.ai.client import _get_proxy
from src.ai.credential_envelope import EphemeralCredential
from src.ai.providers import ai_api_key, normalize_model, provider_for_model
from src.config import AI_PROVIDERS, AI_TIMEOUT_SECONDS


# ── 共享 httpx 客户端（避免每次请求新建 AsyncClient 句柄泄漏） ──


_HTTPX_CLIENT: httpx.AsyncClient | None = None


def get_shared_http_client() -> httpx.AsyncClient:
    """进程级单例 httpx 客户端，lifespan 关闭时统一释放。"""
    global _HTTPX_CLIENT
    if _HTTPX_CLIENT is None:
        kwargs: dict[str, Any] = {"timeout": AI_TIMEOUT_SECONDS}
        proxy = _get_proxy()
        if proxy:
            kwargs["proxy"] = proxy
        _HTTPX_CLIENT = httpx.AsyncClient(**kwargs)
    return _HTTPX_CLIENT


async def close_shared_http_client() -> None:
    """lifespan 关闭时由 server.py 调用，统一释放底层连接。"""
    global _HTTPX_CLIENT
    if _HTTPX_CLIENT is not None:
        await _HTTPX_CLIENT.aclose()
        _HTTPX_CLIENT = None


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

    def __init__(
        self,
        model: str | None = None,
        client: AsyncOpenAI | None = None,
        credential: EphemeralCredential | None = None,
    ):
        self._credential = credential
        if credential is not None:
            self.model = credential.model_id
            self.provider = credential.provider_id
            if model and model != credential.model_id:
                raise RuntimeError("Agent 请求模型与用户凭据不匹配。")
            if credential.protocol == "anthropic":
                self._client = None
                self._owned_http_client = False
                return
            self._client = AsyncOpenAI(
                api_key=credential.api_key,
                base_url=credential.base_url,
                http_client=get_shared_http_client(),
            )
            self._owned_http_client = False
            return

        self.model = normalize_model(model)
        self.provider = provider_for_model(self.model)
        if client is not None:
            self._client = client
            self._owned_http_client = False
            return

        api_key = ai_api_key(self.provider)
        if not api_key:
            label = AI_PROVIDERS[self.provider]["label"]
            raise RuntimeError(f"未设置 {label} API Key，AI 功能暂不可用。")
        base_url = AI_PROVIDERS[self.provider]["url"].replace("/chat/completions", "/v1")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=get_shared_http_client(),
        )
        self._owned_http_client = False

    async def aclose(self) -> None:
        """显式释放 gateway 持有的资源。httpx client 是全局共享的，这里不重复关闭。"""
        # AsyncOpenAI 本身没有 aclose；http_client 是模块级单例。
        # 仍然提供这个方法是为了让调用方在 lifespan/finally 中表达意图。
        self._client = None  # type: ignore[assignment]

    async def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ModelStreamEvent]:
        requested_model = model or self.model
        if self._credential is not None:
            if requested_model != self.model:
                raise RuntimeError("Agent 请求模型与用户凭据不匹配。")
            if self._credential.protocol == "anthropic":
                async for event in self._stream_anthropic(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield event
                return
        else:
            requested_model = normalize_model(requested_model)

        request: dict[str, Any] = {
            "model": requested_model,
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

    @staticmethod
    def _anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for item in messages:
            role = item.get("role")
            if role == "system":
                system_parts.append(str(item.get("content") or ""))
                continue
            if role == "assistant":
                blocks: list[dict[str, Any]] = []
                if item.get("content"):
                    blocks.append({"type": "text", "text": str(item["content"])})
                for call in item.get("tool_calls") or []:
                    function = call.get("function") or {}
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "input": arguments,
                    })
                converted.append({"role": "assistant", "content": blocks})
                continue
            if role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": str(item.get("tool_call_id") or ""),
                        "content": str(item.get("content") or ""),
                    }],
                })
                continue
            if role == "user":
                converted.append({"role": "user", "content": str(item.get("content") or "")})
        return "\n\n".join(part for part in system_parts if part), converted

    async def _stream_anthropic(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[ModelStreamEvent]:
        if self._credential is None:
            raise RuntimeError("缺少用户模型凭据。")
        system, converted = self._anthropic_messages(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": converted,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{
                "name": item.get("function", {}).get("name", ""),
                "description": item.get("function", {}).get("description", ""),
                "input_schema": item.get("function", {}).get("parameters", {
                    "type": "object", "properties": {},
                }),
            } for item in tools]
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.provider == "deepseek":
            headers["x-api-key"] = self._credential.api_key
        else:
            headers["Authorization"] = f"Bearer {self._credential.api_key}"
        url = f"{self._credential.base_url.rstrip('/')}/v1/messages"
        client_kwargs: dict[str, Any] = {"timeout": AI_TIMEOUT_SECONDS}
        proxy = _get_proxy()
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.status_code in {401, 403}:
            raise RuntimeError("API Key 无效或没有该模型权限。")
        if response.status_code == 429:
            raise RuntimeError("模型额度不足或请求过于频繁。")
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError("模型服务暂时不可用。")
        data = response.json()
        usage = data.get("usage") or {}
        yield ModelStreamEvent(
            type="usage",
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
        calls: list[NativeToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                yield ModelStreamEvent(type="delta", content=str(block["text"]))
            elif block.get("type") == "tool_use":
                calls.append(NativeToolCall(
                    id=str(block.get("id") or ""),
                    name=str(block.get("name") or ""),
                    arguments=block.get("input") if isinstance(block.get("input"), dict) else {},
                ))
        if calls:
            yield ModelStreamEvent(type="tool_calls", tool_calls=calls)
        yield ModelStreamEvent(type="done", finish_reason=str(data.get("stop_reason") or "stop"))
