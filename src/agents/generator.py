"""AI 出题 Agent —— 使用 Instructor 做结构化生成和校验。

改造要点：
- generate: chat_structured(response_model=GeneratedQuestion)
- verify: chat_structured(response_model=VerificationResult)
- 替代原来的 call_ai(json_mode=True) + extract_json_object() + 手动 validate
"""

from __future__ import annotations

import json
import random
import uuid
from typing import Any

from src.ai.client import AIClient
from src.models.schemas import GeneratedQuestion, VerificationResult
from src.models import ObjectiveQuestion
from src.db.database import (
    text_hash,
    public_question,
    normalize_choice_answer,
    normalize_fill,
    fill_candidates,
)
from .prompts import QUESTION_GEN_SYSTEM_PROMPT, QUESTION_VERIFY_SYSTEM_PROMPT


def _safe_seed_questions(bank) -> list[Any]:
    return [
        question
        for question in bank.questions
        if not any("疑似" in note or "为空" in note for note in question.suspicious)
    ]


def generate_ai_question(
    client: AIClient,
    bank,
    db,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """AI 生成新题目 —— 使用 Instructor 结构化输出。

    原来的 pipeline:
    1. call_ai(json_mode=True) → extract_json_object()
    2. normalize_ai_item() + validate_ai_item()
    3. verify_ai_item() 又是一次 LLM 调用 + extract_json_object()

    现在的 pipeline:
    1. client.chat_structured(response_model=GeneratedQuestion) → 自动验证
    2. client.chat_structured(response_model=VerificationResult) → 自动验证
    """
    model = payload.get("model")
    qtype = payload.get("qtype") or "单选题"
    if qtype not in {"单选题", "多选题", "填空题", "判断题"}:
        raise ValueError("AI 出题题型不支持。")

    user_id = payload.get("user_id", 0)
    user_context = ""
    if user_id > 0:
        profile = db.get_user_profile(user_id)
        if profile and profile.get("weak_concepts"):
            weak = profile["weak_concepts"]
            weak_types = [t for t, acc in profile.get("type_accuracy", {}).items() if acc < 0.5]
            user_context = f"\n学生弱项章节：{', '.join(weak)}。薄弱题型：{', '.join(weak_types) if weak_types else '无'}。请针对薄弱知识点出题。"

    # 选择种子题目
    source_id = payload.get("source_question_id")
    source = None
    if source_id:
        source = bank.by_id.get(int(source_id))
    if not source:
        seeds = _safe_seed_questions(bank)
        same_type = [item for item in seeds if item.qtype == qtype]
        source = random.choice(same_type or seeds)

    existing_hashes = db.get_all_question_stems_and_hashes()

    prompt = json.dumps({
        "source_question": public_question(source, include_answer=True),
        "target_type": qtype,
        "existing_stems_hashes": existing_hashes[:50],
        "requirements": [
            "根据 source_question 的知识点生成一道全新的数据结构期末练习题。",
            "不要照抄原题数字和问法。确保生成的题目与任何已有题目都不重复。",
            "必须输出 JSON 对象，不要 Markdown。",
            "字段必须包含 qtype, stem, options, answer, analysis。",
            "stem 和 analysis 可以使用 Markdown 表格、行内公式 $...$、代码块和列表来表达公式、矩阵、复杂度或步骤。",
            "选择题 options 使用 A, B, C, D；判断题用 A=对, B=错。",
            "填空题 options 为空数组，answer 为可直接批改的标准答案。",
            user_context if user_context else "",
        ],
    }, ensure_ascii=False)

    # Step 1: 生成题目（Instructor 自动验证结构）
    item: GeneratedQuestion = client.chat_structured(
        [
            {"role": "system", "content": QUESTION_GEN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_model=GeneratedQuestion,
        model=model,
        temperature=0.25,
        max_tokens=900,
    )

    # 转为 dict 以兼容后续处理
    item_dict = {
        "qtype": item.qtype,
        "stem": item.stem,
        "options": item.options,
        "answer": item.answer,
        "analysis": item.analysis,
    }
    item_dict = _normalize_ai_item(item_dict, qtype)
    _validate_ai_item(item_dict)

    # Step 2: 去重检查
    stem_hash = text_hash(item_dict["stem"])
    if db.is_question_duplicate(stem_hash):
        raise ValueError("AI 生成的题目与已有题目重复，请重新生成。")

    # Step 3: 二次校验（Instructor 自动验证）
    _verify_ai_item(client, model, item_dict, source)

    # Step 4: 保存
    ai_id = db.record_ai_question(item_dict, model, source.id)
    db.record_generated_question(stem_hash, ai_id)

    return {
        "id": ai_id,
        "model": model,
        "source_question_id": source.id,
        "question": {
            "id": ai_id,
            "qtype": item_dict["qtype"],
            "stem": item_dict["stem"],
            "options": item_dict.get("options", []),
            "analysis": item_dict.get("analysis", ""),
        },
    }


def _normalize_ai_item(item: dict[str, Any], fallback_type: str) -> dict[str, Any]:
    """规范化 AI 生成的题目字段。"""
    qtype = item.get("qtype") or item.get("type") or fallback_type
    options = item.get("options") or []
    if isinstance(options, dict):
        options = [{"key": key, "text": str(value)} for key, value in options.items()]
    normalized_options = []
    import re
    for option in options:
        if isinstance(option, dict):
            key = str(option.get("key") or option.get("label") or "").strip().upper()
            text = str(option.get("text") or option.get("value") or "").strip()
        else:
            match = re.match(r"^([A-H])\.\s*(.*)$", str(option).strip())
            key = match.group(1) if match else ""
            text = match.group(2) if match else str(option)
        if key:
            normalized_options.append({"key": key, "text": text})
    answer = item.get("answer") or item.get("correct_answer") or item.get("correctAnswer") or ""
    if isinstance(answer, list):
        answer = "".join(str(part) for part in answer)
    return {
        "qtype": qtype,
        "stem": str(item.get("stem") or item.get("question") or "").strip(),
        "options": normalized_options,
        "answer": str(answer).strip(),
        "analysis": str(item.get("analysis") or item.get("explanation") or "").strip(),
    }


def _validate_ai_item(item: dict[str, Any]) -> None:
    """验证 AI 生成的题目字段合法性。"""
    if item["qtype"] not in {"单选题", "多选题", "填空题", "判断题"}:
        raise ValueError("AI 生成题型不合法。")
    if len(item["stem"]) < 8:
        raise ValueError("AI 生成题干过短。")
    if not item["answer"]:
        raise ValueError("AI 生成答案为空。")
    if item["qtype"] in {"单选题", "多选题", "判断题"}:
        keys = {option["key"] for option in item["options"]}
        if len(keys) < 2:
            raise ValueError("AI 选择题选项不足。")
        answer_keys = set(normalize_choice_answer(item["answer"]))
        if not answer_keys or not answer_keys.issubset(keys):
            raise ValueError("AI 答案不在选项中。")
    if item["qtype"] == "填空题" and item["options"]:
        raise ValueError("AI 填空题不应包含选项。")


def _verify_ai_item(
    client: AIClient, model: str, item: dict[str, Any], source: Any,
) -> None:
    """AI 二次校验 —— 使用 Instructor 结构化输出。"""
    verdict: VerificationResult = client.chat_structured(
        [
            {"role": "system", "content": QUESTION_VERIFY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({
                    "task": "检查生成题是否知识点清楚且答案正确。",
                    "source_question": public_question(source, include_answer=True),
                    "generated_question": item,
                }, ensure_ascii=False),
            },
        ],
        response_model=VerificationResult,
        model=model,
        temperature=0.0,
        max_tokens=500,
    )

    if not verdict.valid:
        raise ValueError(f"AI 二次校验未通过: {verdict.reason}")

    checked_answer = verdict.answer.strip()
    if checked_answer:
        if item["qtype"] == "多选题":
            from src.db.database import normalize_multi_answer
            same = normalize_multi_answer(checked_answer) == normalize_multi_answer(item["answer"])
        elif item["qtype"] in {"单选题", "判断题"}:
            same = normalize_choice_answer(checked_answer) == normalize_choice_answer(item["answer"])
        else:
            same = normalize_fill(checked_answer) in fill_candidates(item["answer"])
        if not same:
            raise ValueError("AI 二次校验答案与生成答案不一致。")
