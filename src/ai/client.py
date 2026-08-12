"""AI 客户端 —— Instructor + OpenAI SDK 封装。

核心改造：
- `chat()` 替代原 call_ai() 的普通调用
- `chat_structured()` 替代 json_mode=True + extract_json_object()
- `chat_stream()` 替代 call_ai_stream()
"""

from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Generator, TypeVar

import instructor
from openai import OpenAI
from pydantic import BaseModel

from src.config import AI_PROVIDERS, AI_TIMEOUT_SECONDS, AI_MAX_RETRIES
from .providers import (
    AIProviderError,
    ai_api_key,
    ai_error_message,
    current_default_model,
    normalize_model,
    normalize_provider,
    provider_for_model,
)

T = TypeVar("T", bound=BaseModel)

# ── 代理支持 ──


def _get_proxy() -> str | None:
    """解析环境变量中的 HTTP 代理设置。"""
    for scheme, names in {
        "http": ("HTTP_PROXY", "http_proxy"),
        "https": ("HTTPS_PROXY", "https_proxy"),
    }.items():
        value = next(
            (os.environ.get(name) for name in names if os.environ.get(name)), ""
        )
        if value:
            return value
    return None


# ── 手动 JSON 解析（用作无 Instructor 时的 fallback） ──


def extract_json_object(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象（用作 fallback）。"""
    text = text.strip()
    if text.startswith("```"):
        import re

        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


# ── 响应解析（从 server.py 搬移） ──


def ai_content_to_text(value: Any) -> str:
    """递归从嵌套结构中提取文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(ai_content_to_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            if key in value:
                text = ai_content_to_text(value.get(key))
                if text:
                    return text
        return ""
    return str(value)


def ai_choice_text(choice: dict[str, Any]) -> str:
    """从 API 响应的 choice 中提取文本。"""
    visible_chunks: list[str] = []
    fallback_chunks: list[str] = []
    for container_key in ("message", "delta"):
        container = choice.get(container_key)
        if not isinstance(container, dict):
            continue
        for field in ("content", "text"):
            text = ai_content_to_text(container.get(field))
            if text:
                visible_chunks.append(text)
        text = ai_content_to_text(container.get("reasoning_content"))
        if text:
            fallback_chunks.append(text)
    for field in ("content", "text"):
        text = ai_content_to_text(choice.get(field))
        if text:
            visible_chunks.append(text)
    if not visible_chunks:
        for field in ("reasoning_content", "reasoning"):
            text = ai_content_to_text(choice.get(field))
            if text:
                fallback_chunks.append(text)
    return "".join(visible_chunks or fallback_chunks)


def ai_response_text(data: dict[str, Any], provider: str) -> str:
    """从完整 API 响应中提取文本。"""
    try:
        choices = data["choices"]
        if not choices:
            raise IndexError
        text = ai_choice_text(choices[0])
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError(
            ai_error_message(provider, f"响应格式异常: {data}")
        ) from exc
    if not text:
        raise AIProviderError(
            ai_error_message(provider, f"响应内容为空: {data}")
        )
    return text


# ── AIClient ──


class AIClient:
    """统一的 AI 客户端，使用 Instructor 实现结构化输出。

    使用方式：
        client = AIClient(model="deepseek-v4-flash")

        # 普通文本对话
        reply = client.chat(messages, temperature=0.7)

        # 结构化输出（替代 json_mode + extract_json_object）
        result = client.chat_structured(messages, response_model=IntentResult)

        # 流式输出
        for delta in client.chat_stream(messages):
            yield delta
    """

    def __init__(self, model: str | None = None):
        self.model = normalize_model(model)
        self.provider = provider_for_model(self.model)
        api_key = ai_api_key(self.provider)
        if not api_key:
            raise AIProviderError(
                f"未设置 {AI_PROVIDERS[self.provider]['label']} API Key，AI 功能暂不可用。"
            )
        # 构建 base_url：将 /chat/completions 替换为 /v1
        base_url = AI_PROVIDERS[self.provider]["url"].replace(
            "/chat/completions", "/v1"
        )
        # OpenAI SDK 客户端
        http_client_kwargs: dict[str, Any] = {"timeout": AI_TIMEOUT_SECONDS}
        proxy = _get_proxy()
        if proxy:
            import httpx

            http_client_kwargs["http_client"] = httpx.Client(proxy=proxy)

        self._openai = OpenAI(
            api_key=api_key,
            base_url=base_url,
            **http_client_kwargs,
        )
        # Instructor 包装
        self._instructor = instructor.from_openai(self._openai)
        self._retry_count = 0

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        _retry_count: int = 0,
    ) -> str:
        """普通文本对话，返回字符串。"""
        model = normalize_model(model) if model else self.model
        try:
            response = self._openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            return self._handle_error(exc, messages, model, temperature, max_tokens, _retry_count)

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        _retry_count: int = 0,
    ) -> T:
        """结构化输出 —— 使用 Instructor 自动解析和验证。

        替代原来的 call_ai(..., json_mode=True) + extract_json_object()。
        返回已验证的 Pydantic 模型实例。
        """
        model = normalize_model(model) if model else self.model
        try:
            return self._instructor.chat.completions.create(
                model=model,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            # Instructor 内部通常会重试，如果最终还是失败，尝试 fallback
            try:
                raw = self.chat(
                    messages, model=model, temperature=temperature,
                    max_tokens=max_tokens, _retry_count=_retry_count,
                )
                data = extract_json_object(raw)
                return response_model(**data)
            except Exception:
                return self._handle_error(
                    exc, messages, model, temperature, max_tokens, _retry_count
                )

    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        """带工具调用的对话 —— 使用 Native Function Calling。

        返回 {"content": str, "tool_calls": list | None}
        """
        model = normalize_model(model) if model else self.model
        try:
            response = self._openai.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            result: dict[str, Any] = {"content": "", "tool_calls": None}
            if choice.message.content:
                result["content"] = choice.message.content
            if choice.message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in choice.message.tool_calls
                ]
            return result
        except Exception as exc:
            # Fallback: 如果 tool calling 不支持，降级为普通对话 + 手动解析
            raw = self.chat(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
            result = {"content": raw, "tool_calls": None}
            # 尝试检测 prompt 注入格式的工具调用
            try:
                parsed = extract_json_object(raw)
                if "tool_call" in parsed:
                    result["tool_calls"] = [parsed["tool_call"]]
            except (json.JSONDecodeError, ValueError):
                pass
            return result

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1600,
    ) -> Generator[str, None, None]:
        """流式对话，yield delta 字符串。"""
        model = normalize_model(model) if model else self.model
        try:
            stream = self._openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            error_msg = str(exc)
            if "429" in error_msg or "rate" in error_msg.lower():
                yield f"\n[AI 接口触发频率限制，请稍后重试。]"
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                yield f"\n[AI 接口请求超时，请切换模型或稍后重试。]"
            else:
                yield f"\n[AI 调用出错: {error_msg[:200]}]"

    def _handle_error(
        self,
        exc: Exception,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        retry_count: int,
    ) -> Any:
        """统一的错误处理和重试逻辑。"""
        error_msg = str(exc).lower()
        is_rate_limit = "429" in error_msg or "rate" in error_msg.lower()
        is_timeout = "timeout" in error_msg or "timed out" in error_msg

        if (is_rate_limit or is_timeout) and retry_count < AI_MAX_RETRIES:
            time.sleep(2**retry_count)
            return self.chat(
                messages, model=model, temperature=temperature,
                max_tokens=max_tokens, _retry_count=retry_count + 1,
            )
        raise AIProviderError(
            ai_error_message(self.provider, f"接口调用失败: {exc}")
        ) from exc


def get_ai_client(provider: str | None = None) -> AIClient:
    """工厂函数 —— 根据当前配置创建 AI 客户端。"""
    model = current_default_model()
    if provider:
        normalized = normalize_model(
            AI_PROVIDERS[normalize_provider(provider)]["default_model"]
        )
        return AIClient(model=normalized)
    return AIClient(model=model)
