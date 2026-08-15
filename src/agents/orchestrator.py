"""Single asynchronous Tutor Agent execution core."""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from typing import Any, AsyncIterator, Protocol

from src.agents.context import TurnContext
from src.agents.events import AgentEvent, EventFactory
from src.agents.prompts import SOCRATIC_SYSTEM_PROMPT
from src.agents.router import classify_intent
from src.ai.gateway import ModelStreamEvent, NativeToolCall


class ModelGateway(Protocol):
    async def stream(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]: ...


class AgentTools(Protocol):
    def as_openai_tools(self) -> list[dict[str, Any]]: ...
    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class TutorOrchestrator:
    """Run routing, model streaming and authorized native tools as one state machine."""

    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway

    async def stream(
        self,
        context: TurnContext,
        tool_registry: AgentTools | None = None,
    ) -> AsyncIterator[AgentEvent]:
        factory = EventFactory(uuid.uuid4().hex)
        yield factory.create("meta", mode=context.mode, model=context.model or "default")
        route = classify_intent(context.message)
        yield factory.create("route", intent=route.intent, confidence=route.confidence)

        try:
            async with asyncio.timeout(context.budget.timeout_seconds):
                async for event in self._execute(context, factory, tool_registry):
                    yield event
        except TimeoutError:
            yield factory.create(
                "error",
                code="timeout",
                message="Agent 本轮调用超过超时预算。",
            )
        except Exception as exc:
            yield factory.create(
                "error",
                code="agent_error",
                message=str(exc)[:500] or "Agent 执行失败。",
            )

    async def _execute(
        self,
        context: TurnContext,
        factory: EventFactory,
        tool_registry: AgentTools | None,
    ) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = context.model_messages(SOCRATIC_SYSTEM_PROMPT)
        tools = tool_registry.as_openai_tools() if tool_registry else None
        tool_rounds = 0
        estimated_output_tokens = 0
        provider_input_tokens = 0
        provider_output_tokens = 0

        while True:
            remaining = context.budget.max_output_tokens - estimated_output_tokens
            if remaining <= 0:
                yield factory.create(
                    "error",
                    code="output_token_budget_exceeded",
                    message="Agent 本轮输出已达到 Token 预算。",
                )
                return

            turn_text = ""
            tool_calls: list[NativeToolCall] = []
            finish_reason = "stop"
            async for item in self.gateway.stream(
                messages=messages,
                tools=tools,
                model=context.model,
                temperature=0.65,
                max_tokens=remaining,
            ):
                if item.type == "delta" and item.content:
                    chunk_tokens = max(1, math.ceil(len(item.content.encode("utf-8")) / 4))
                    estimated_output_tokens += chunk_tokens
                    if estimated_output_tokens > context.budget.max_output_tokens:
                        yield factory.create(
                            "error",
                            code="output_token_budget_exceeded",
                            message="Agent 本轮输出已达到 Token 预算。",
                        )
                        return
                    turn_text += item.content
                    yield factory.create("delta", content=item.content)
                elif item.type == "tool_calls":
                    tool_calls = item.tool_calls or []
                elif item.type == "usage":
                    provider_input_tokens = item.input_tokens or provider_input_tokens
                    provider_output_tokens = item.output_tokens or provider_output_tokens
                elif item.type == "done":
                    finish_reason = item.finish_reason or finish_reason

            if not tool_calls:
                if provider_input_tokens or provider_output_tokens:
                    yield factory.create(
                        "usage",
                        input_tokens=provider_input_tokens,
                        output_tokens=provider_output_tokens or estimated_output_tokens,
                    )
                yield factory.create("done", finish_reason=finish_reason)
                return

            if tool_registry is None:
                yield factory.create(
                    "error",
                    code="tools_unavailable",
                    message="当前入口不允许使用本地用户工具。",
                )
                return
            if tool_rounds >= context.budget.max_tool_rounds:
                yield factory.create(
                    "error",
                    code="tool_round_budget_exceeded",
                    message="Agent 本轮工具调用轮数已达到预算。",
                )
                return

            assistant_calls = []
            invalid_call_ids: set[str] = set()
            for call in tool_calls:
                if "_invalid_json" in call.arguments:
                    yield factory.create(
                        "error",
                        code="invalid_tool_arguments",
                        tool_call_id=call.id,
                        tool_name=call.name,
                        message=f"工具 {call.name} 的参数不是合法 JSON。",
                    )
                    invalid_call_ids.add(call.id)
                    continue
                assistant_calls.append({
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                })

            # 安全网：如果本轮所有工具调用都是非法 JSON（没有可执行的有效工具），
            # 直接终止对话，避免无限重发同一条坏调用。
            if not assistant_calls:
                yield factory.create(
                    "error",
                    code="invalid_tool_arguments",
                    message="本轮所有工具调用的参数都不是合法 JSON，已终止。",
                )
                return
            messages.append({
                "role": "assistant",
                "content": turn_text or None,
                "tool_calls": assistant_calls,
            })

            for call in tool_calls:
                if call.id in invalid_call_ids:
                    # 跳过本轮 JSON 损坏的工具调用，但仍把它以错误形式追加到
                    # messages，避免模型下一轮再次重新触发同一条调用。
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(
                            {"error": "invalid_json_arguments"},
                            ensure_ascii=False,
                        ),
                    })
                    continue
                yield factory.create(
                    "tool_start",
                    tool_call_id=call.id,
                    tool_name=call.name,
                    arguments=call.arguments,
                )
                result = await asyncio.to_thread(
                    tool_registry.execute,
                    call.name,
                    call.arguments,
                )
                yield factory.create(
                    "tool_result",
                    tool_call_id=call.id,
                    tool_name=call.name,
                    result=result,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            tool_rounds += 1


__all__ = ["ModelStreamEvent", "NativeToolCall", "TutorOrchestrator"]
