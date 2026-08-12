"""题库数据模型 —— 客观题、讨论题、作业题 dataclass 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ObjectiveQuestion:
    """客观题（单选题/多选题/填空题/判断题）"""

    id: int
    source_order: int
    source_num: str
    qtype: str
    chapter: str
    stem: str
    options: list[dict[str, str]]
    answer: str
    raw_correct: str
    score: int | None
    images: list[str] = field(default_factory=list)
    repaired: bool = False
    suspicious: list[str] = field(default_factory=list)
    stem_hash: str = ""


@dataclass
class DiscussionQuestion:
    """讨论题"""

    id: int
    source_order: int
    chapter: str
    prompt: str
    stem_hash: str


@dataclass
class AssignmentQuestion:
    """作业题（简答题/填空题）"""

    id: int
    source_order: int
    source_num: str
    qtype: str
    chapter: str
    stem: str
    options: list[dict[str, str]]
    answer: str
    answer_source: str
    raw_correct: str
    images: list[str] = field(default_factory=list)
    suspicious: list[str] = field(default_factory=list)
    stem_hash: str = ""
