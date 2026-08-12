"""Agent 工具注册表 —— 工具定义 + 执行入口。"""

from __future__ import annotations

import json
from typing import Any

from src.db.database import (
    public_bank_question,
    extract_concepts_from_stem,
    grade_answer,
)


def get_tool_definitions() -> list[dict[str, Any]]:
    """返回 OpenAI Function Calling 格式的工具定义列表。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_question",
                "description": "获取题目详情（不含答案），用于了解学生正在练习的题目",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_id": {
                            "type": "integer",
                            "description": "题库中的题目ID",
                        }
                    },
                    "required": ["question_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_student_profile",
                "description": "获取学生的学习画像，包括弱项章节、题型正确率、概念掌握度",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "在题库中搜索包含特定关键词的题目",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，如'二叉树'、'哈希表'",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_similar_questions",
                "description": "获取与指定题目知识点相似的题目，用于推荐同类练习",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_id": {
                            "type": "integer",
                            "description": "参考题目ID",
                        },
                        "count": {
                            "type": "integer",
                            "description": "返回数量，默认3",
                            "default": 3,
                        },
                    },
                    "required": ["question_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_answer",
                "description": "批改学生的答案，返回正确/错误和分析",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_id": {
                            "type": "integer",
                            "description": "题目ID",
                        },
                        "user_answer": {
                            "type": "string",
                            "description": "学生提交的答案",
                        },
                    },
                    "required": ["question_id", "user_answer"],
                },
            },
        },
    ]


class ToolRegistry:
    """工具注册表 —— 统一管理所有 Agent 可用工具。"""

    def __init__(self, bank, db, user_id: int):
        self._bank = bank
        self._db = db
        self._user_id = user_id

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """执行指定工具，返回结果字典。"""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"success": False, "error": f"未知工具: {name}"}
        try:
            return handler(args)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def as_openai_tools(self) -> list[dict[str, Any]]:
        """返回 OpenAI Function Calling 格式的工具定义。"""
        return get_tool_definitions()

    # ── 工具实现 ──

    def _tool_get_question(self, args: dict) -> dict[str, Any]:
        qid = int(args.get("question_id", 0))
        q = self._bank.by_id.get(qid)
        if q:
            return {"success": True, "data": public_bank_question(q, include_answer=False)}
        return {"success": False, "error": f"题目{qid}不存在"}

    def _tool_get_student_profile(self, args: dict) -> dict[str, Any]:
        # 用户身份来自服务端创建 ToolRegistry 时的可信上下文，绝不采信模型参数。
        uid = self._user_id
        profile = self._db.get_user_profile(uid) or self._db.update_user_profile(uid)
        concepts = self._db.get_concept_mastery(uid)
        return {"success": True, "data": {"profile": profile, "concept_mastery": concepts}}

    def _tool_search_knowledge_base(self, args: dict) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "查询词不能为空"}
        results = []
        query_lower = query.lower()
        for q in self._bank.questions:
            if query_lower in q.stem.lower():
                results.append(public_bank_question(q, include_answer=False))
            if len(results) >= 5:
                break
        return {"success": True, "data": {"query": query, "matches": results, "count": len(results)}}

    def _tool_get_similar_questions(self, args: dict) -> dict[str, Any]:
        qid = int(args.get("question_id", 0))
        cnt = int(args.get("count", 3))
        source = self._bank.by_id.get(qid)
        if not source:
            return {"success": False, "error": f"题目{qid}不存在"}
        source_concepts = set(extract_concepts_from_stem(source.stem))
        scored = []
        for q in self._bank.questions:
            if q.id == qid:
                continue
            q_concepts = set(extract_concepts_from_stem(q.stem))
            overlap = len(source_concepts & q_concepts) if source_concepts else 0
            if overlap > 0:
                scored.append((q, overlap))
        scored.sort(key=lambda x: -x[1])
        selected = [public_bank_question(q, include_answer=False) for q, _ in scored[:cnt]]
        return {"success": True, "data": {"question_id": qid, "similar": selected, "count": len(selected)}}

    def _tool_check_answer(self, args: dict) -> dict[str, Any]:
        qid = int(args.get("question_id", 0))
        user_answer = args.get("user_answer", "")
        q = self._bank.by_id.get(qid)
        if not q:
            return {"success": False, "error": f"题目{qid}不存在"}
        if hasattr(q, "answer_source"):  # AssignmentQuestion
            return {"success": False, "error": "简答题不支持自动批改"}
        result = grade_answer(q, user_answer)
        return {"success": True, "data": {
            "is_correct": result["is_correct"],
            "analysis": result["analysis"],
        }}
