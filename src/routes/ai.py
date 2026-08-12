"""AI 路由 —— /api/ai/*, /api/question/ai/*"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.models.schemas import (
    AIGenerateRequest,
    AIAnswerRequest,
    AITutorRequest,
    QuestionAIRequest,
    AISupplementRequest,
)
from src.ai.client import AIClient, get_ai_client
from src.ai.streaming import sse_stream
from src.agents import (
    SOCRATIC_SYSTEM_PROMPT,
    classify_intent,
    run_multi_agent_pipeline,
    generate_ai_question as agent_generate_question,
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
    require_auth,
    parse_auth_header,
    make_error_response,
)

router = APIRouter(tags=["ai"])


def _get_ai_client(model: str | None = None) -> AIClient:
    return AIClient(model=model)


# ── AI 出题 ──


@router.post("/ai/generate")
async def ai_generate(req: AIGenerateRequest, request: Request):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        session = parse_auth_header(request.headers.get("Authorization"), db=db)
        user_id = session["user_id"] if session else 0
        client = _get_ai_client(req.model)
        return agent_generate_question(
            client, exam_bank, db,
            {"model": req.model, "qtype": req.qtype, "source_question_id": req.source_question_id, "user_id": user_id},
        )
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/answer")
async def ai_answer(req: AIAnswerRequest, request: Request):
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
        db.record_attempt(0, "ai", item["qtype"], req.answer, item["answer"], result["is_correct"])
        result["analysis"] = item.get("analysis") or result["analysis"]
        return result
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/supplement")
async def ai_supplement(req: AISupplementRequest, request: Request):
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
async def socratic_tutor(req: AITutorRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        model = req.model
        client = _get_ai_client(model)
        message = req.message.strip()
        if not message:
            raise ValueError("请输入你的问题或思考。")

        question_context = ""
        if req.question_id:
            q = exam_bank.by_id.get(req.question_id)
            if q:
                question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

        history = []
        conv_id = req.conversation_id
        if conv_id:
            convs = db.get_conversations(_auth["user_id"], 1)
            for conv in convs:
                if conv["id"] == int(conv_id):
                    history = conv["messages"]
                    break

        messages = [
            {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT + question_context},
            *history[-10:],
            {"role": "user", "content": message},
        ]
        reply = client.chat(messages, model=model, temperature=0.7, max_tokens=1200)

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        if conv_id:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(history, ensure_ascii=False), time.time(), int(conv_id)),
                )
            new_id = int(conv_id)
        else:
            new_id = db.save_conversation(
                _auth["user_id"], req.question_id, "tutor", history,
            )
        return {
            "conversation_id": new_id, "reply": reply,
            "model": model or "default", "mode": "socratic_tutor",
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/tutor/stream")
async def socratic_tutor_stream(req: AITutorRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        model = req.model
        client = _get_ai_client(model)
        message = req.message.strip()
        if not message:
            raise ValueError("请输入你的问题或思考。")

        question_context = ""
        if req.question_id:
            q = exam_bank.by_id.get(req.question_id)
            if q:
                question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

        history = []
        conv_id = req.conversation_id
        if conv_id:
            convs = db.get_conversations(_auth["user_id"], 1)
            for conv in convs:
                if conv["id"] == int(conv_id):
                    history = conv["messages"]
                    break

        messages = [
            {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT + question_context},
            *history[-10:],
            {"role": "user", "content": message},
        ]

        def stream():
            full_reply = ""
            for delta in client.chat_stream(messages, model=model, temperature=0.7, max_tokens=1200):
                full_reply += delta
                yield {"delta": delta}
            # 保存对话
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": full_reply})
            if conv_id:
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(history, ensure_ascii=False), time.time(), int(conv_id)),
                    )
            else:
                db.save_conversation(_auth["user_id"], req.question_id, "tutor", history)

        return sse_stream(stream())
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


# ── 多智能体导师 ──


@router.post("/ai/multi-agent/tutor")
async def multi_agent_tutor(req: AITutorRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        model = req.model
        client = _get_ai_client(model)
        message = req.message.strip()
        if not message:
            raise ValueError("请输入你的问题或思考。")

        question_context = ""
        if req.question_id:
            q = exam_bank.by_id.get(req.question_id)
            if q:
                question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

        history = []
        conv_id = req.conversation_id
        if conv_id:
            convs = db.get_conversations(_auth["user_id"], 1)
            for conv in convs:
                if conv["id"] == int(conv_id):
                    history = [{"role": m["role"], "content": m["content"]} for m in conv["messages"]]
                    break

        user_profile = db.get_user_profile(_auth["user_id"])
        tool_registry = ToolRegistry(exam_bank, db, _auth["user_id"])

        # Router（规则优先 + LLM fallback）
        intent_result = classify_intent(client, model, message, question_context, history)
        intent = intent_result.intent

        # Multi-agent pipeline
        pipeline_result = run_multi_agent_pipeline(
            client, model, message, question_context, history,
            user_profile, tool_registry, intent=intent,
        )
        reply = pipeline_result["reply"]

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        if conv_id:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(history, ensure_ascii=False), time.time(), int(conv_id)),
                )
            new_id = int(conv_id)
        else:
            new_id = db.save_conversation(
                _auth["user_id"], req.question_id, "multi_agent", history,
            )

        return {
            "conversation_id": new_id,
            "reply": reply,
            "model": model or "default",
            "mode": "multi_agent_tutor",
            "pipeline": {
                "intent": intent,
                "intent_confidence": intent_result.confidence,
                **pipeline_result.get("pipeline", {}),
            },
        }
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


@router.post("/ai/multi-agent/tutor/stream")
async def multi_agent_tutor_stream(req: AITutorRequest, request: Request, _auth=Depends(require_auth)):
    try:
        db = request.app.state.db
        exam_bank = request.app.state.exam_bank
        model = req.model
        client = _get_ai_client(model)
        message = req.message.strip()
        if not message:
            raise ValueError("请输入你的问题或思考。")

        question_context = ""
        if req.question_id:
            q = exam_bank.by_id.get(req.question_id)
            if q:
                question_context = f"\n\n【学生正在练习的题目】\n{public_bank_question(q, include_answer=False)}"

        history = []
        conv_id = req.conversation_id
        if conv_id:
            convs = db.get_conversations(_auth["user_id"], 1)
            for conv in convs:
                if conv["id"] == int(conv_id):
                    history = [{"role": m["role"], "content": m["content"]} for m in conv["messages"]]
                    break

        user_profile = db.get_user_profile(_auth["user_id"])
        tool_registry = ToolRegistry(exam_bank, db, _auth["user_id"])

        intent_result = classify_intent(client, model, message, question_context, history)
        intent = intent_result.intent

        pipeline_result = run_multi_agent_pipeline(
            client, model, message, question_context, history,
            user_profile, tool_registry, intent=intent,
        )
        reply = pipeline_result["reply"]

        # 流式输出最终回复
        def stream():
            yield {"delta": reply}
            # 如果是工具调用触发的，已包含最终回复
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            if conv_id:
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE ai_conversations SET messages_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(history, ensure_ascii=False), time.time(), int(conv_id)),
                    )
            else:
                db.save_conversation(_auth["user_id"], req.question_id, "multi_agent", history)

        return sse_stream(stream())
    except Exception as exc:
        status, body = make_error_response(exc)
        return request.app.state._json_response(body, status)


# ── 题目 AI 讲解 ──


@router.post("/question/ai")
async def question_ai(req: QuestionAIRequest, request: Request):
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
async def question_ai_stream(req: QuestionAIRequest, request: Request):
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
