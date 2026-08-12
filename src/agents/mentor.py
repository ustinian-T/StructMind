"""Mentor Agent —— 苏格拉底式教学导师。

改造要点：
- 使用 Native Function Calling 替代 prompt 注入 + 正则解析
- 使用 Instructor 的 response_model 做结构化分析
- 支持流式和非流式两种模式
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.ai.client import AIClient
from src.models.schemas import AnalysisResult, EvaluationResult
from src.tools.registry import ToolRegistry
from .prompts import (
    SOCRATIC_SYSTEM_PROMPT,
    ANALYSIS_SYSTEM_PROMPT,
    EVALUATOR_SYSTEM_PROMPT,
)


def analyze_student(
    client: AIClient,
    model: str,
    user_profile: dict[str, Any] | None,
    question_context: str,
    history: list[dict[str, str]],
    message: str,
    intent: str,
) -> AnalysisResult:
    """内部分析学生情况 —— 使用 Instructor 结构化输出。

    替代原来的 _analysis_agent() + extract_json_object()。
    """
    profile_summary = {}
    if user_profile:
        profile_summary = {
            "weak_concepts": user_profile.get("weak_concepts", []),
            "strong_concepts": user_profile.get("strong_concepts", []),
            "type_accuracy": user_profile.get("type_accuracy", {}),
            "overall_accuracy": user_profile.get("accuracy", 0),
        }

    prompt = json.dumps({
        "task": "私密分析这位数据结构学生的学习状况。你的输出不会直接展示给学生，而是传递给 Mentor 助教作为教学参考。",
        "student_intent": intent,
        "student_message": message,
        "question_context": question_context[:800] if question_context else "",
        "profile_summary": profile_summary,
    }, ensure_ascii=False)

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    return client.chat_structured(
        messages,
        response_model=AnalysisResult,
        model=model,
        temperature=0.1,
        max_tokens=500,
    )


def mentor_respond(
    client: AIClient,
    model: str,
    message: str,
    question_context: str,
    history: list[dict[str, str]],
    analysis: AnalysisResult,
    tool_registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """苏格拉底导师回复 —— 支持 Native Function Calling。

    返回 {"reply": str, "tool_calls": list | None}

    改造前：Mentor 输出特殊 JSON {"tool_call": {...}}，代码正则解析
    改造后：使用 OpenAI 兼容的 tools 参数，模型原生返回 tool_calls
    """
    hint_level = analysis.hint_level
    gaps = analysis.knowledge_gaps
    approach = analysis.recommended_approach
    key_concepts = analysis.key_concepts_to_address

    system_prompt = f"""{SOCRATIC_SYSTEM_PROMPT}

## 本轮教学指引（内部，勿直接告知学生）
- 教学策略: {approach}
- 提示力度: {"轻微提示" if hint_level <= 1 else "适度引导" if hint_level == 2 else "深入讲解"}{"（学生需要更多帮助）" if hint_level >= 3 else ""}
- 需关注的概念: {', '.join(key_concepts) if key_concepts else '视对话进展而定'}
- 学生可能的知识空缺: {', '.join(gaps) if gaps else '未知'}
"""

    msgs: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt + (question_context if question_context else "")},
    ]
    if history:
        msgs.extend(history[-10:])
    msgs.append({"role": "user", "content": message})

    if tool_registry:
        # 使用 Native Function Calling
        result = client.chat_with_tools(
            msgs,
            tools=tool_registry.as_openai_tools(),
            model=model,
            temperature=0.7,
            max_tokens=1200,
        )
        return {
            "reply": result["content"],
            "tool_calls": result["tool_calls"],
        }
    else:
        # 纯文本回复
        reply = client.chat(msgs, model=model, temperature=0.7, max_tokens=1200)
        return {"reply": reply, "tool_calls": None}


def evaluator_assess(
    client: AIClient,
    model: str,
    student_response: str,
    analysis: AnalysisResult,
    question_context: str,
) -> EvaluationResult:
    """评估学生理解程度 —— 使用 Instructor 结构化输出。

    替代原来的 _evaluator_agent() + extract_json_object()。
    """
    prompt = json.dumps({
        "task": "评估学生在数据结构对话中的理解程度，决定下一步行动",
        "student_response": student_response[:600],
        "previous_analysis": {
            "knowledge_gaps": analysis.knowledge_gaps,
            "key_concepts": analysis.key_concepts_to_address,
        },
        "question_context": question_context[:400] if question_context else "",
    }, ensure_ascii=False)

    messages = [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    return client.chat_structured(
        messages,
        response_model=EvaluationResult,
        model=model,
        temperature=0.0,
        max_tokens=300,
    )


def run_multi_agent_pipeline(
    client: AIClient,
    model: str,
    message: str,
    question_context: str,
    history: list[dict[str, str]],
    user_profile: dict[str, Any] | None,
    tool_registry: ToolRegistry | None,
    intent: str = "concept_understanding",
) -> dict[str, Any]:
    """多智能体管道主入口。

    Pipeline:
    1. Analysis Agent → 内部分析学生状况
    2. Mentor Agent → 生成教学回复（可调用工具）
    3. （可选）Evaluator Agent → 评估理解程度

    Returns:
        {"reply": str, "pipeline": {...}}
    """
    # Step 1: Analysis
    analysis = analyze_student(
        client, model, user_profile, question_context, history, message, intent,
    )

    # Step 2: Mentor（可能触发工具调用）
    mentor_result = mentor_respond(
        client, model, message, question_context, history, analysis, tool_registry,
    )

    reply = mentor_result["reply"]
    tool_calls = mentor_result.get("tool_calls")

    # Step 3: 如果 Mentor 调用了工具，将结果反馈给 Mentor
    tool_results = None
    if tool_calls and tool_registry:
        tool_results = []
        for tc in tool_calls:
            result = tool_registry.execute(tc["name"], tc["arguments"])
            tool_results.append({"tool": tc["name"], "result": result})

        # 将工具结果反馈给 Mentor 生成最终回复
        feedback_msg = f"[工具调用结果]\n" + json.dumps(
            [{"tool": tr["tool"], "result": tr["result"]} for tr in tool_results],
            ensure_ascii=False,
        )
        msgs = [
            {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT + question_context},
        ]
        if history:
            msgs.extend(history[-8:])
        msgs.append({"role": "user", "content": message})
        msgs.append({"role": "assistant", "content": reply})
        msgs.append({"role": "user", "content": feedback_msg})
        reply = client.chat(msgs, model=model, temperature=0.7, max_tokens=1200)

    return {
        "reply": reply,
        "pipeline": {
            "intent": intent,
            "hint_level": analysis.hint_level,
            "knowledge_gaps": analysis.knowledge_gaps,
            "recommended_approach": analysis.recommended_approach,
            "tool_called": tool_calls[0]["name"] if tool_calls else None,
            "tool_results_count": len(tool_results) if tool_results else 0,
        },
    }
