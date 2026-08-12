"""Pydantic 模型 —— FastAPI 请求/响应 + Instructor 结构化 LLM 输出。

这些模型用于：
1. FastAPI 路由的请求体验证和响应序列化
2. Instructor 库的 response_model —— 替代手动 extract_json_object() + setdefault()
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Instructor 结构化 LLM 输出模型
# ═══════════════════════════════════════════════════════════════

class IntentResult(BaseModel):
    """Router Agent 输出 —— 学生提问意图分类"""

    intent: Literal[
        "concept_understanding", "problem_solving", "clarification", "review_request"
    ]
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    reason: str = ""


class AnalysisResult(BaseModel):
    """Analysis Agent 输出 —— 学生内部分析（不展示给学生）"""

    knowledge_gaps: list[str] = Field(default_factory=list)
    recommended_approach: str = "引导式提问"
    hint_level: int = Field(default=2, ge=1, le=3)
    key_concepts_to_address: list[str] = Field(default_factory=list)
    estimated_difficulty_for_student: Literal["easy", "medium", "hard"] = "medium"


class EvaluationResult(BaseModel):
    """Evaluator Agent 输出 —— 学生理解程度评估"""

    understanding_level: int = Field(default=3, ge=1, le=5)
    should_continue: bool = True
    next_action: Literal[
        "deeper_discussion", "move_on", "review_concept", "give_practice", "summarize"
    ] = "deeper_discussion"
    notes: str = ""


class GeneratedQuestion(BaseModel):
    """AI 出题 —— 生成的题目结构"""

    qtype: Literal["单选题", "多选题", "填空题", "判断题"]
    stem: str = Field(min_length=8)
    options: list[dict[str, str]] = Field(default_factory=list)
    answer: str = Field(min_length=1)
    analysis: str = ""


class VerificationResult(BaseModel):
    """AI 出题二次校验结果"""

    valid: bool
    answer: str = ""
    reason: str = ""


class OptionSupplementResult(BaseModel):
    """AI 选项补全结果"""

    options: dict[str, str] = Field(default_factory=dict)
    reason: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class DiscussionFeedback(BaseModel):
    """AI 讨论题批改反馈"""

    score: float = Field(default=0, ge=0, le=10)
    level: str = "参考反馈"
    reference_answer: str = ""
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    suggestion: str = ""


class AssignmentFeedback(BaseModel):
    """AI 作业题批改反馈"""

    score: float = Field(default=0, ge=0, le=10)
    level: str = "参考反馈"
    verdict: str = ""
    reference_answer: str = ""
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    suggestion: str = ""


# ═══════════════════════════════════════════════════════════════
# FastAPI 请求模型
# ═══════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    account: str
    password: str


class RegisterRequest(BaseModel):
    account: str
    password: str
    name: str
    phone: str


class ApproveRequest(BaseModel):
    user_id: int
    approved: bool = True


class SessionRequest(BaseModel):
    bank_id: str | None = None
    mode: str = "sequence"
    types: list[str] | None = None
    chapters: list[str] | None = None
    count: int | None = None
    question_ids: list[int] | None = None


class AnswerRequest(BaseModel):
    question_id: int
    bank_id: str | None = None
    answer: Any = None
    attempt_token: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    time_spent_seconds: float = Field(default=0, ge=0, le=86_400)


class AIGenerateRequest(BaseModel):
    model: str | None = None
    qtype: str = "单选题"
    source_question_id: int | None = None
    user_id: int = 0


class AIAnswerRequest(BaseModel):
    ai_question_id: str | None = None
    id: str | None = None
    answer: Any = None


class AITutorRequest(BaseModel):
    model: str | None = None
    message: str
    question_id: int | None = None
    conversation_id: int | None = None
    bank_id: str | None = None
    mode: str = "explain"


class AgentServiceTutorRequest(BaseModel):
    """Sanitized tutor turn forwarded by the trusted uniCloud proxy."""

    external_user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=12_000)
    history: list[dict[str, Any]] = Field(default_factory=list)
    question_context: str = Field(default="", max_length=20_000)
    conversation_id: str | int | None = None
    question_id: str | int | None = None
    mode: Literal["standard", "multi_agent"] = "standard"
    model: str | None = None


class QuestionAIRequest(BaseModel):
    question_id: int
    bank_id: str | None = None
    model: str | None = None
    mode: str = "explain"
    message: str = ""


class AssignmentGradeRequest(BaseModel):
    question_id: int | None = None
    assignment_id: int | None = None
    answer: str
    model: str | None = None


class DiscussionGradeRequest(BaseModel):
    discussion_id: int
    answer: str
    model: str | None = None


class RecommendRequest(BaseModel):
    count: int = 10
    types: list[str] | None = None
    bank_id: str = "exam"


class ConceptUpdateRequest(BaseModel):
    concept: str
    is_correct: bool = False


class ReviewFeedbackRequest(BaseModel):
    concept: str = Field(min_length=1, max_length=128)
    feedback: Literal["too_easy", "just_right", "too_hard"]
    learning_event_id: str | None = Field(default=None, max_length=128)


class ConfigUpdateRequest(BaseModel):
    provider: str | None = None
    default_provider: str | None = None
    model: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    zhipu_api_key: str | None = None
    deepseek_api_key: str | None = None
    api_keys: dict[str, str] | None = None
    clear_provider: str | None = None
    clear_api_key: bool | None = None


class CommunityPostRequest(BaseModel):
    title: str
    content: str
    question_id: int | None = None
    bank_id: str | None = None


class CommunityReplyRequest(BaseModel):
    post_id: int
    content: str


class BankUploadRequest(BaseModel):
    name: str
    questions: list[dict[str, Any]]


class BankGetRequest(BaseModel):
    bank_id: int


class GeneratePlanRequest(BaseModel):
    exam_date: str
    daily_minutes: int = Field(ge=10, le=480)
    timezone: str = "Asia/Shanghai"
    evaluated_at: str | None = None


class LearningNoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    user_content: str = Field(default="", max_length=50_000)
    tags: list[str] = Field(default_factory=list)
    concept: str | None = Field(default=None, max_length=128)


class LearningNoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    user_content: str | None = Field(default=None, max_length=50_000)
    tags: list[str] | None = None
    concept: str | None = Field(default=None, max_length=128)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class AISupplementRequest(BaseModel):
    question_id: int
    model: str | None = None


# ═══════════════════════════════════════════════════════════════
# FastAPI 通用响应模型
# ═══════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    error: str


class OKResponse(BaseModel):
    ok: bool = True
