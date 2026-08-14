"""AI 路由 —— /api/ai/*, /api/question/ai/*"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from src.models.schemas import (
    AIGenerateRequest,
    AIAnswerRequest,
    AITutorRequest,
    QuestionAIRequest,
    AISupplementRequest,
    AgentServiceTutorRequest,
)
from src.ai.client import AIClient, get_ai_client
from src.ai.gateway import AsyncModelGateway
from src.ai.credential_envelope import EphemeralCredential, decrypt_agent_envelope
from src.ai.streaming import sse_stream
from src.agents import (
    generate_ai_question as agent_generate_question,
)
from src.agents.context import AgentBudget, TurnContext
from src.agents.events import AgentEvent
from src.agents.orchestrator import TutorOrchestrator
from src.config import (
    AGENT_MAX_HISTORY_MESSAGES,
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MAX_TOOL_ROUNDS,
    AGENT_TIMEOUT_SECONDS,
)
from src.tools.registry import ToolRegistry
from src.db.database import (
    public_bank_question,
    public_discussion,
    grade_answer,
)
from src.routes.deps import (
    get_db,
    get_exam_bank,
    get_assignment_bank,
    selected_bank,
    consume_ai_quota,
    require_ai_access,
    require_agent_service,
    make_error_response,
)
from src.learning.rules import CONCEPT_KEYWORDS

router = APIRouter(tags=["ai"])
websocket_router = APIRouter(tags=["ai"])


def _get_ai_client(model: str | None = None) -> AIClient:
    return AIClient(model=model)


def _agent_budget() -> AgentBudget:
    return AgentBudget(
        max_tool_rounds=AGENT_MAX_TOOL_ROUNDS,
        max_output_tokens=AGENT_MAX_OUTPUT_TOKENS,
        timeout_seconds=AGENT_TIMEOUT_SECONDS,
        max_history_messages=AGENT_MAX_HISTORY_MESSAGES,
    )


def _new_orchestrator(
    request_or_websocket,
    model: str | None,
    credential: EphemeralCredential | None = None,
) -> TutorOrchestrator:
    factory = getattr(request_or_websocket.app.state, "agent_gateway_factory", None)
    gateway = factory(model) if factory else AsyncModelGateway(model=model, credential=credential)
    return TutorOrchestrator(gateway)


def _question_context(exam_bank, question_id: int | None) -> str:
    if not question_id:
        return ""
    question = exam_bank.by_id.get(int(question_id))
    if not question:
        return ""
    return json.dumps(
        public_bank_question(question, include_answer=False),
        ensure_ascii=False,
    )


def _prepare_local_turn(
    request_or_websocket,
    req: AITutorRequest,
    auth: dict[str, Any],
    mode: str,
) -> tuple[TurnContext, list[dict[str, str]], ToolRegistry]:
    db = request_or_websocket.app.state.db
    exam_bank = request_or_websocket.app.state.exam_bank
    history: list[dict[str, str]] = []
    if req.conversation_id:
        conversation = db.get_conversation(int(req.conversation_id), auth["user_id"])
        if not conversation:
            raise KeyError("对话不存在。")
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in conversation["messages"]
            if item.get("role") in {"user", "assistant"}
        ]
    context = TurnContext(
        user_id=int(auth["user_id"]),
        message=req.message,
        history=history,
        question_context=_question_context(exam_bank, req.question_id),
        user_profile=db.get_user_profile(int(auth["user_id"])),
        conversation_id=req.conversation_id,
        question_id=req.question_id,
        mode="multi_agent" if mode == "multi_agent" else "standard",
        model=req.model,
        budget=_agent_budget(),
    )
    return context, history, ToolRegistry(exam_bank, db, int(auth["user_id"]))


async def _stream_local_turn(
    request_or_websocket,
    context: TurnContext,
    history: list[dict[str, str]],
    tool_registry: ToolRegistry,
) -> AsyncIterator[AgentEvent]:
    db = request_or_websocket.app.state.db
    orchestrator = _new_orchestrator(request_or_websocket, context.model)
    reply_parts: list[str] = []
    async for event in orchestrator.stream(context, tool_registry):
        if event.type == "delta" and event.content:
            reply_parts.append(event.content)
        if event.type == "done":
            reply = "".join(reply_parts)
            updated = [
                *history,
                {"role": "user", "content": context.message},
                {"role": "assistant", "content": reply},
            ]
            if context.conversation_id:
                db.update_conversation(
                    int(context.conversation_id),
                    int(context.user_id),
                    updated,
                )
                conversation_id = int(context.conversation_id)
            else:
                conversation_id = db.save_conversation(
                    int(context.user_id),
                    int(context.question_id) if context.question_id else None,
                    "multi_agent" if context.mode == "multi_agent" else "tutor",
                    updated,
                )
            db.refresh_conversation_summary(
                int(context.user_id), conversation_id,
                [name for name, _keywords in CONCEPT_KEYWORDS],
            )
            event = event.model_copy(update={"conversation_id": conversation_id})
        yield event


async def _collect_local_turn(
    request: Request,
    context: TurnContext,
    history: list[dict[str, str]],
    tool_registry: ToolRegistry,
) -> dict[str, Any]:
    events = [
        event.model_dump(mode="json")
        async for event in _stream_local_turn(request, context, history, tool_registry)
    ]
    reply = "".join(
        event.get("content", "") for event in events if event["type"] == "delta"
    )
    done = next((event for event in reversed(events) if event["type"] == "done"), {})
    return {
        "protocol": "structmind.agent.v1",
        "events": events,
        "reply": reply,
        "message": reply,
        "conversation_id": done.get("conversation_id"),
        "mode": context.mode,
        "model": context.model or "default",
    }


@websocket_router.websocket("/ws/tutor")
async def tutor_websocket(websocket: WebSocket):
    """Authenticated WebSocket adapter over the shared Agent event stream."""
    await websocket.accept()
    db = websocket.app.state.db
    exam_bank = websocket.app.state.exam_bank
    session: dict[str, Any] | None = None
    try:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")
            if message_type == "auth":
                session = db.get_session(str(payload.get("token") or ""))
                if not session or session.get("status") != "approved":
                    await websocket.send_json({"type": "error", "error": "登录状态已失效，请重新登录。"})
                    await websocket.close(code=1008)
                    return
                await websocket.send_json({"type": "auth", "ok": True})
                continue
            if message_type != "message":
                await websocket.send_json({"type": "error", "error": "不支持的消息类型。"})
                continue
            if not session:
                session = db.get_session(str(payload.get("token") or ""))
            if not session or session.get("status") != "approved":
                await websocket.send_json({"type": "error", "error": "请先登录。"})
                await websocket.close(code=1008)
                return

            try:
                consume_ai_quota(websocket.app, int(session["user_id"]))
            except Exception as exc:
                await websocket.send_json({"type": "error", "error": getattr(exc, "detail", str(exc))})
                continue

            try:
                req = AITutorRequest(
                    message=str(payload.get("message") or ""),
                    conversation_id=payload.get("conversation_id"),
                    question_id=payload.get("question_id"),
                    model=payload.get("model"),
                    mode=str(payload.get("mode") or "standard"),
                )
                mode = "multi_agent" if req.mode in {"multi-agent", "multi_agent"} else "standard"
                context, history, tool_registry = _prepare_local_turn(
                    websocket, req, session, mode,
                )
                async for event in _stream_local_turn(
                    websocket, context, history, tool_registry,
                ):
                    await websocket.send_json(event.model_dump(mode="json"))
            except Exception as exc:
                await websocket.send_json({
                    "protocol": "structmind.agent.v1",
                    "type": "error",
                    "message": str(exc),
                })
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except (RuntimeError, WebSocketDisconnect):
            return


# ── AI 出题 ──


@router.post("/ai/generate")
async def ai_generate(
    req: AIGenerateRequest,
    request: Request,
    _auth=Depends(require_ai_access),
):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        client = _get_ai_client(req.model)
        return agent_generate_question(
            client, exam_bank, db,
            {"model": req.model, "qtype": req.qtype, "source_question_id": req.source_question_id, "user_id": _auth["user_id"]},
        )
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/answer")
async def ai_answer(
    req: AIAnswerRequest,
    request: Request,
    _auth=Depends(require_ai_access),
):
    try:
        db = request.app.state.db
        ai_id = str(req.ai_question_id or req.id or "")
        item = db.get_ai_question(ai_id)
        if not item:
            raise KeyError("AI 题不存在。")
        from src.models import ObjectiveQuestion
        pseudo_question = ObjectiveQuestion(
            id=0, source_order=0, source_num="AI", qtype=item["qtype"],
            chapter="AI 出题", stem=item["stem"], options=item["options"],
            answer=item["answer"], raw_correct=item["answer"], score=None,
        )
        result = grade_answer(pseudo_question, req.answer)
        db.record_attempt(
            0, "ai", item["qtype"], req.answer, item["answer"],
            result["is_correct"], user_id=_auth["user_id"],
        )
        result["analysis"] = item.get("analysis") or result["analysis"]
        return result
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/supplement")
async def ai_supplement(
    req: AISupplementRequest,
    request: Request,
    _auth=Depends(require_ai_access),
):
    try:
        exam_bank = request.app.state.exam_bank
        question = exam_bank.by_id.get(req.question_id)
        if not question:
            raise KeyError("题目不存在。")
        client = _get_ai_client(req.model)
        prompt = json.dumps({
            "task": "根据题干、现有选项、正确答案，补全缺失或残缺的选项文本，并说明依据。不要改变正确答案。",
            "question": public_bank_question(question, include_answer=True),
        }, ensure_ascii=False)
        from src.models.schemas import OptionSupplementResult
        suggestion = client.chat_structured(
            [
                {"role": "system", "content": "你是数据结构题库修复员。只输出 JSON，不修改标准答案。"},
                {"role": "user", "content": prompt},
            ],
            response_model=OptionSupplementResult,
            model=req.model,
            temperature=0.0,
            max_tokens=900,
        )
        options = suggestion.options
        if not isinstance(options, dict):
            raise ValueError("AI 补全结果格式不合法。")
        from src.db.database import normalize_choice_answer
        correct = normalize_choice_answer(question.answer)
        if question.qtype in {"单选题", "多选题", "判断题"} and correct:
            option_keys = {key.upper() for key in options.keys()}
            if not set(correct).issubset(option_keys):
                raise ValueError("AI 补全结果没有包含标准答案对应选项。")
        return {"question": public_bank_question(question, include_answer=True), "suggestion": suggestion.model_dump()}
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


# ── 苏格拉底导师（简单模式） ──


@router.post("/ai/tutor")
async def socratic_tutor(req: AITutorRequest, request: Request, _auth=Depends(require_ai_access)):
    try:
        context, history, tools = _prepare_local_turn(request, req, _auth, "standard")
        return await _collect_local_turn(request, context, history, tools)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/tutor/stream")
async def socratic_tutor_stream(req: AITutorRequest, request: Request, _auth=Depends(require_ai_access)):
    try:
        context, history, tools = _prepare_local_turn(request, req, _auth, "standard")
        return sse_stream(_stream_local_turn(request, context, history, tools))
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


# ── 多智能体导师 ──


@router.post("/ai/multi-agent/tutor")
async def multi_agent_tutor(req: AITutorRequest, request: Request, _auth=Depends(require_ai_access)):
    try:
        context, history, tools = _prepare_local_turn(request, req, _auth, "multi_agent")
        return await _collect_local_turn(request, context, history, tools)
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/multi-agent/tutor/stream")
async def multi_agent_tutor_stream(req: AITutorRequest, request: Request, _auth=Depends(require_ai_access)):
    try:
        context, history, tools = _prepare_local_turn(request, req, _auth, "multi_agent")
        return sse_stream(_stream_local_turn(request, context, history, tools))
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/internal/agent/tutor")
async def service_tutor(
    req: AgentServiceTutorRequest,
    request: Request,
    _service=Depends(require_agent_service),
):
    """Credentialed uniCloud adapter; FastAPI remains the only Agent core."""
    credential = decrypt_agent_envelope(
        req.credential_envelope,
        expected_user_id=req.external_user_id,
    )
    if req.model and req.model != credential.model_id:
        raise ValueError("Agent 请求模型与用户凭据不匹配。")
    context = TurnContext(
        user_id=f"external:{req.external_user_id}",
        message=req.message,
        history=req.history,
        question_context=req.question_context,
        conversation_id=req.conversation_id,
        question_id=req.question_id,
        mode=req.mode,
        model=credential.model_id,
        budget=_agent_budget(),
    )
    orchestrator = _new_orchestrator(request, credential.model_id, credential)
    events = [
        event.model_dump(mode="json")
        async for event in orchestrator.stream(context, tool_registry=None)
    ]
    reply = "".join(
        event.get("content", "") for event in events if event["type"] == "delta"
    )
    return {
        "protocol": "structmind.agent.v1",
        "events": events,
        "reply": reply,
        "message": reply,
        "mode": req.mode,
    }


# ── 题目 AI 讲解 ──


@router.post("/question/ai")
async def question_ai(
    req: QuestionAIRequest,
    request: Request,
    _auth=Depends(require_ai_access),
):
    try:
        exam_bank = request.app.state.exam_bank
        assignment_bank = request.app.state.assignment_bank
        bank = selected_bank(req.bank_id, exam_bank, assignment_bank)
        question = bank.by_id.get(req.question_id)
        if not question:
            raise KeyError("题目不存在。")
        mode = req.mode or "explain"
        message = req.message.strip()
        model = req.model
        question_payload = public_bank_question(question, include_answer=True)

        if mode == "check":
            task = "检查这道题的题干、选项和参考答案是否一致，特别说明补全显示或AI参考答案是否影响答案来源。"
        elif mode == "ask" and message:
            task = f"回答学生关于这道题的问题：{message}"
        else:
            task = "讲解这道题的知识点、解题步骤、参考答案依据，以及常见错误。"

        client = _get_ai_client(model)
        reply = client.chat(
            [
                {"role": "system", "content": "你是数据结构课程助教。输出中文Markdown，可使用表格、公式$...$、代码块和列表。不要编造与题干无关的内容。先给结论，再给理由。"},
                {"role": "user", "content": json.dumps({
                    "task": task,
                    "question": question_payload,
                    "requirements": [
                        "如果题目来自补全表，请说明补全只用于显示，标准答案仍来自题库。",
                        "如果作业题答案来源是AI参考答案，请明确它不是Word官方答案。",
                    ],
                }, ensure_ascii=False)},
            ],
            model=model,
            temperature=0.2 if mode != "check" else 0.0,
            max_tokens=1600,
        )
        return {
            "bank_id": bank.bank_id, "question_id": question.id,
            "mode": mode, "model": model or "default", "reply": reply,
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/question/ai/stream")
async def question_ai_stream(
    req: QuestionAIRequest,
    request: Request,
    _auth=Depends(require_ai_access),
):
    try:
        exam_bank = request.app.state.exam_bank
        assignment_bank = request.app.state.assignment_bank
        bank = selected_bank(req.bank_id, exam_bank, assignment_bank)
        question = bank.by_id.get(req.question_id)
        if not question:
            raise KeyError("题目不存在。")
        mode = req.mode or "explain"
        model = req.model
        question_payload = public_bank_question(question, include_answer=True)

        task = "讲解这道题的知识点、解题步骤、参考答案依据，以及常见错误。"
        if mode == "check":
            task = "检查这道题的题干、选项和参考答案是否一致。"
        elif mode == "ask" and req.message.strip():
            task = f"回答学生关于这道题的问题：{req.message.strip()}"

        client = _get_ai_client(model)
        messages = [
            {"role": "system", "content": "你是数据结构课程助教。输出中文Markdown。先给结论，再给理由。"},
            {"role": "user", "content": json.dumps({"task": task, "question": question_payload}, ensure_ascii=False)},
        ]

        def stream():
            for delta in client.chat_stream(messages, model=model, temperature=0.2, max_tokens=1600):
                yield {"delta": delta}

        return sse_stream(stream())
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)
