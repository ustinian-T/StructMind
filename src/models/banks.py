"""题库容器模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .questions import ObjectiveQuestion, DiscussionQuestion, AssignmentQuestion


@dataclass
class QuestionBank:
    """期末考试题库"""

    bank_id: str
    label: str
    docx_path: str
    docx_sha256: str
    questions: list[ObjectiveQuestion]
    discussions: list[DiscussionQuestion]
    audit: list[dict[str, Any]]

    @property
    def by_id(self) -> dict[int, ObjectiveQuestion]:
        return {q.id: q for q in self.questions}

    @property
    def discussion_by_id(self) -> dict[int, DiscussionQuestion]:
        return {q.id: q for q in self.discussions}


@dataclass
class AssignmentBank:
    """作业题库"""

    bank_id: str
    label: str
    docx_path: str
    docx_sha256: str
    questions: list[AssignmentQuestion]
    audit: list[dict[str, Any]]

    @property
    def by_id(self) -> dict[int, AssignmentQuestion]:
        return {q.id: q for q in self.questions}
