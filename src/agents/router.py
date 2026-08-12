"""Deterministic, zero-token routing for Tutor Agent turns."""

from __future__ import annotations

from src.models.schemas import IntentResult


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


def classify_intent(message: str) -> IntentResult:
    """Route without a second model call so streaming can start immediately."""
    return _rule_classify(message) or IntentResult(
        intent="concept_understanding",
        confidence=0.4,
        reason="未命中确定性规则，使用安全默认路由",
    )
