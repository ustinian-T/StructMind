import asyncio

import pytest
from pydantic import ValidationError


def test_turn_context_validates_budgets_and_trims_history():
    from src.agents.context import AgentBudget, TurnContext

    with pytest.raises(ValidationError):
        AgentBudget(max_tool_rounds=-1)

    context = TurnContext(
        user_id=42,
        message="请解释二叉树",
        history=[
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "untrusted"},
            {"role": "user", "content": "u2"},
        ],
        budget=AgentBudget(max_history_messages=2),
    )

    assert context.user_id == 42
    assert context.safe_history() == [
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    assert "42" not in str(context.model_messages("system"))
    assert "untrusted" not in str(context.model_messages("system"))


def test_event_factory_produces_versioned_monotonic_envelopes():
    from src.agents.events import EventFactory

    factory = EventFactory("run-1")
    delta = factory.create("delta", content="你")
    done = factory.create("done", finish_reason="stop")

    assert delta.model_dump(mode="json") == {
        "protocol": "structmind.agent.v1",
        "type": "delta",
        "run_id": "run-1",
        "sequence": 1,
        "timestamp": delta.timestamp.isoformat().replace("+00:00", "Z"),
        "content": "你",
    }
    assert done.sequence == 2
    assert done.type == "done"
    assert done.finish_reason == "stop"


def test_event_rejects_fields_that_do_not_match_type():
    from src.agents.events import AgentEvent

    with pytest.raises(ValidationError):
        AgentEvent(
            protocol="structmind.agent.v1",
            type="delta",
            run_id="run-1",
            sequence=1,
            content=None,
        )

    with pytest.raises(ValidationError):
        AgentEvent(
            protocol="structmind.agent.v1",
            type="tool_result",
            run_id="run-1",
            sequence=1,
            tool_name="get_question",
        )


class FakeGateway:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []

    async def stream(self, *, messages, tools, model, temperature, max_tokens):
        self.requests.append(messages)
        for item in self.turns.pop(0):
            yield item


class FakeTools:
    def __init__(self):
        self.calls = []

    def as_openai_tools(self):
        return [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"success": True, "data": "tool-result"}


async def collect_events(iterator):
    return [event async for event in iterator]


def test_orchestrator_streams_each_model_delta_before_done():
    from src.agents.context import TurnContext
    from src.agents.orchestrator import ModelStreamEvent, TutorOrchestrator

    gateway = FakeGateway([[
        ModelStreamEvent(type="delta", content="逐"),
        ModelStreamEvent(type="delta", content="Token"),
        ModelStreamEvent(type="done", finish_reason="stop"),
    ]])
    events = asyncio.run(collect_events(TutorOrchestrator(gateway).stream(
        TurnContext(user_id=1, message="解释栈")
    )))

    assert [event.type for event in events] == ["meta", "route", "delta", "delta", "done"]
    assert [event.content for event in events if event.type == "delta"] == ["逐", "Token"]
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


def test_orchestrator_uses_native_assistant_and_tool_messages():
    from src.agents.context import TurnContext
    from src.agents.orchestrator import ModelStreamEvent, NativeToolCall, TutorOrchestrator

    gateway = FakeGateway([
        [
            ModelStreamEvent(
                type="tool_calls",
                tool_calls=[NativeToolCall(id="call-1", name="lookup", arguments={"q": "树"})],
            ),
            ModelStreamEvent(type="done", finish_reason="tool_calls"),
        ],
        [
            ModelStreamEvent(type="delta", content="这是结果"),
            ModelStreamEvent(type="done", finish_reason="stop"),
        ],
    ])
    tools = FakeTools()
    events = asyncio.run(collect_events(TutorOrchestrator(gateway).stream(
        TurnContext(user_id=1, message="查一下树"), tools
    )))

    second_request = gateway.requests[1]
    assistant = second_request[-2]
    tool_message = second_request[-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call-1"
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"q": "树"}'
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"
    assert "tool-result" in tool_message["content"]
    assert all(item.get("role") != "user" or "[工具调用结果]" not in item.get("content", "") for item in second_request)
    assert tools.calls == [("lookup", {"q": "树"})]
    assert [event.type for event in events].count("tool_start") == 1
    assert [event.type for event in events].count("tool_result") == 1


def test_orchestrator_stops_at_tool_round_budget():
    from src.agents.context import AgentBudget, TurnContext
    from src.agents.orchestrator import ModelStreamEvent, NativeToolCall, TutorOrchestrator

    gateway = FakeGateway([[
        ModelStreamEvent(
            type="tool_calls",
            tool_calls=[NativeToolCall(id="call-1", name="lookup", arguments={})],
        ),
        ModelStreamEvent(type="done", finish_reason="tool_calls"),
    ]])
    tools = FakeTools()
    events = asyncio.run(collect_events(TutorOrchestrator(gateway).stream(
        TurnContext(
            user_id=1,
            message="查资料",
            budget=AgentBudget(max_tool_rounds=0),
        ),
        tools,
    )))

    assert events[-1].type == "error"
    assert events[-1].code == "tool_round_budget_exceeded"
    assert tools.calls == []


def test_orchestrator_rejects_malformed_native_tool_arguments():
    from src.agents.context import TurnContext
    from src.agents.orchestrator import ModelStreamEvent, NativeToolCall, TutorOrchestrator

    gateway = FakeGateway([[
        ModelStreamEvent(
            type="tool_calls",
            tool_calls=[NativeToolCall(
                id="call-bad",
                name="lookup",
                arguments={"_invalid_json": "{bad"},
            )],
        ),
        ModelStreamEvent(type="done", finish_reason="tool_calls"),
    ]])
    tools = FakeTools()
    events = asyncio.run(collect_events(TutorOrchestrator(gateway).stream(
        TurnContext(user_id=1, message="查资料"),
        tools,
    )))

    assert events[-1].type == "error"
    assert events[-1].code == "invalid_tool_arguments"
    assert tools.calls == []


def test_orchestrator_enforces_output_token_and_timeout_budgets():
    from src.agents.context import AgentBudget, TurnContext
    from src.agents.orchestrator import ModelStreamEvent, TutorOrchestrator

    token_gateway = FakeGateway([[
        ModelStreamEvent(type="delta", content="x" * 160),
        ModelStreamEvent(type="done", finish_reason="stop"),
    ]])
    token_events = asyncio.run(collect_events(TutorOrchestrator(token_gateway).stream(
        TurnContext(
            user_id=1,
            message="test",
            budget=AgentBudget(max_output_tokens=32),
        )
    )))
    assert token_events[-1].type == "error"
    assert token_events[-1].code == "output_token_budget_exceeded"

    class SlowGateway:
        async def stream(self, **kwargs):
            await asyncio.sleep(0.05)
            yield ModelStreamEvent(type="done", finish_reason="stop")

    timeout_events = asyncio.run(collect_events(TutorOrchestrator(SlowGateway()).stream(
        TurnContext(
            user_id=1,
            message="test",
            budget=AgentBudget(timeout_seconds=0.01),
        )
    )))
    assert timeout_events[-1].type == "error"
    assert timeout_events[-1].code == "timeout"


def test_async_gateway_normalizes_progressive_text_and_fragmented_tool_calls():
    from types import SimpleNamespace

    from src.ai.gateway import AsyncModelGateway

    def chunk(*, content=None, tool_calls=None, finish_reason=None):
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(
                finish_reason=finish_reason,
                delta=SimpleNamespace(content=content, tool_calls=tool_calls),
            )],
        )

    class FakeStream:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            self.iterator = iter(self.items)
            return self

        async def __anext__(self):
            try:
                return next(self.iterator)
            except StopIteration:
                raise StopAsyncIteration

    class Completions:
        async def create(self, **_kwargs):
            return FakeStream([
                chunk(content="逐"),
                chunk(content="Token"),
                chunk(tool_calls=[SimpleNamespace(
                    index=0,
                    id="call-1",
                    function=SimpleNamespace(name="lookup", arguments='{"q":'),
                )]),
                chunk(tool_calls=[SimpleNamespace(
                    index=0,
                    id=None,
                    function=SimpleNamespace(name=None, arguments='"树"}'),
                )], finish_reason="tool_calls"),
            ])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    gateway = AsyncModelGateway(model="glm-5.1", client=fake_client)
    events = asyncio.run(collect_events(gateway.stream(
        messages=[{"role": "user", "content": "test"}],
        tools=[],
        model="glm-5.1",
        temperature=0,
        max_tokens=100,
    )))

    assert [event.content for event in events if event.type == "delta"] == ["逐", "Token"]
    tool_event = next(event for event in events if event.type == "tool_calls")
    assert tool_event.tool_calls[0].id == "call-1"
    assert tool_event.tool_calls[0].name == "lookup"
    assert tool_event.tool_calls[0].arguments == {"q": "树"}
    assert events[-1].type == "done"
    assert events[-1].finish_reason == "tool_calls"
