"""Router Agent —— 学生意图分类。

改造要点：
- 规则引擎优先（零延迟），LLM 作为 fallback
- 使用 Instructor 的 response_model 替代 extract_json_object()
"""

from __future__ import annotations

import json
from typing import Any

from src.ai.client import AIClient
from src.models.schemas import IntentResult
from .prompts import ROUTER_SYSTEM_PROMPT


# ── 规则引擎（快速分类，无需 LLM 调用） ──

ROUTING_RULES: dict[str, list[str]] = {
    "problem_solving": [
        "怎么做", "不会做", "不会", "怎么解", "解题", "帮我看看这道",
        "这题", "选什么", "选哪个", "答案是多少", "填什么",
    ],
    "concept_understanding": [
        "什么是", "区别", "概念", "定义", "特点", "特征",
        "优缺点", "原理", "为什么", "解释一下", "讲一下",
    ],
    "clarification": [
        "没听懂", "再说一遍", "什么意思", "不理解", "不明白",
        "刚才说的", "能再解释", "换个方式",
    ],
    "review_request": [
        "复习", "总结", "推荐", "类似题目", "再来一题",
        "练习", "出题", "测试一下",
    ],
}


def _rule_classify(message: str) -> IntentResult | None:
    """规则引擎分类 —— 如果匹配成功返回结果，否则返回 None。"""
    msg_lower = message.lower().strip()
    scores: dict[str, int] = {}
    for intent, keywords in ROUTING_RULES.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[intent] = score
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    # 需要至少两个关键词匹配才认为是高置信度
    confidence = min(0.9, 0.5 + 0.15 * scores[best])
    return IntentResult(intent=best, confidence=confidence, reason=f"关键词匹配: {best}")


# ── LLM Router（fallback） ──


def _llm_classify(
    client: AIClient,
    model: str,
    message: str,
    question_context: str,
    history: list[dict[str, str]],
) -> IntentResult:
    """LLM 意图分类 —— 仅在规则无法匹配时使用。"""
    hist_summary = ""
    if history:
        last_msgs = history[-6:]
        hist_summary = "\n".join(
            f"{'学生' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
            for m in last_msgs
        )

    prompt = json.dumps({
        "task": "将学生对数据结构习题的以下提问划分到唯一类别",
        "categories": {
            "concept_understanding": "学生对概念/知识点不理解，需要讲解",
            "problem_solving": "学生在解具体题目，寻求解题思路",
            "clarification": "学生对之前的讲解有疑问，要求进一步解释",
            "review_request": "学生要求复习、总结或推荐类似题目",
        },
        "student_message": message,
        "question_context": question_context[:500] if question_context else "",
        "recent_history": hist_summary,
    }, ensure_ascii=False)

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    return client.chat_structured(
        messages,
        response_model=IntentResult,
        model=model,
        temperature=0.0,
        max_tokens=300,
    )


def classify_intent(
    client: AIClient,
    model: str,
    message: str,
    question_context: str = "",
    history: list[dict[str, str]] | None = None,
) -> IntentResult:
    """意图分类入口 —— 规则优先，LLM fallback。

    Args:
        client: AI 客户端
        model: 模型名称
        message: 学生消息
        question_context: 关联的题目上下文
        history: 对话历史

    Returns:
        IntentResult: 已验证的意图分类结果（Pydantic 模型）
    """
    history = history or []

    # 1. 尝试规则分类
    result = _rule_classify(message)
    if result is not None:
        return result

    # 2. LLM fallback
    return _llm_classify(client, model, message, question_context, history)
