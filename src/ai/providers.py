"""AI Provider 配置 —— 多服务商支持、模型管理、API Key 解析。"""

from __future__ import annotations

import os
from typing import Any

from src.config import AI_PROVIDERS, ALLOWED_MODELS, MODEL_ALIASES, RUNTIME_CONFIG


class AIProviderError(RuntimeError):
    """AI 服务商通用错误。"""


class DeepSeekError(AIProviderError):
    """DeepSeek 特定错误。"""


def ai_error_message(provider: str, message: str) -> str:
    return f"{AI_PROVIDERS[provider]['label']} {message}"


def normalize_provider(provider: str | None) -> str:
    provider = (
        provider or str(RUNTIME_CONFIG.get("default_provider") or "zhipu")
    ).strip().lower()
    if provider not in AI_PROVIDERS:
        raise ValueError(f"不支持的 AI 服务商: {provider}")
    return provider


def provider_for_model(model: str) -> str:
    for provider_id, config in AI_PROVIDERS.items():
        if model in config["models"]:
            return provider_id
    raise ValueError(f"不支持的模型: {model}")


def normalize_model(model: str | None, provider: str | None = None) -> str:
    if not model:
        return current_default_model()
    model = MODEL_ALIASES.get(str(model).strip(), str(model).strip())
    if model not in ALLOWED_MODELS:
        raise ValueError(f"不支持的模型: {model}")
    if provider and model not in AI_PROVIDERS[normalize_provider(provider)]["models"]:
        raise ValueError(f"{AI_PROVIDERS[normalize_provider(provider)]['label']} 不支持模型: {model}")
    return model


def current_default_model() -> str:
    raw = MODEL_ALIASES.get(
        str(RUNTIME_CONFIG.get("default_model") or "").strip(),
        str(RUNTIME_CONFIG.get("default_model") or "").strip(),
    )
    if raw in ALLOWED_MODELS:
        return raw
    provider = normalize_provider(str(RUNTIME_CONFIG.get("default_provider") or "zhipu"))
    return str(AI_PROVIDERS[provider]["default_model"])


def ai_api_key(provider: str) -> str:
    provider = normalize_provider(provider)
    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    runtime_key = str(runtime_keys.get(provider) or "").strip()
    if runtime_key:
        return runtime_key
    for env_name in AI_PROVIDERS[provider]["env"]:
        value = os.environ.get(env_name)
        if value:
            return value.strip()
    return ""


def api_key_source(provider: str | None = None) -> str:
    provider = normalize_provider(provider or provider_for_model(current_default_model()))
    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    if str(runtime_keys.get(provider) or "").strip():
        return "runtime"
    if any(os.environ.get(env_name) for env_name in AI_PROVIDERS[provider]["env"]):
        return "environment"
    return "none"


def key_preview(provider: str | None = None) -> str:
    provider = normalize_provider(provider or provider_for_model(current_default_model()))
    key = ai_api_key(provider)
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def provider_payload(provider_id: str) -> dict[str, Any]:
    config = AI_PROVIDERS[provider_id]
    return {
        "id": provider_id,
        "label": config["label"],
        "models": config["models"],
        "default_model": config["default_model"],
        "ai_configured": bool(ai_api_key(provider_id)),
        "api_key_source": api_key_source(provider_id),
        "key_preview": key_preview(provider_id),
    }


def config_payload() -> dict[str, Any]:
    model = current_default_model()
    provider = provider_for_model(model)
    return {
        "models": sorted(ALLOWED_MODELS),
        "providers": [provider_payload(pid) for pid in AI_PROVIDERS],
        "default_provider": provider,
        "default_model": model,
        "ai_configured": bool(ai_api_key(provider)),
        "api_key_source": api_key_source(provider),
        "key_preview": key_preview(provider),
        "timeout_seconds": 120,
    }


def update_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider = normalize_provider(
        payload.get("provider") or payload.get("default_provider")
        or RUNTIME_CONFIG.get("default_provider")
    )
    if "model" in payload or "default_model" in payload:
        model = normalize_model(
            payload.get("model") or payload.get("default_model"), provider=None
        )
        provider = provider_for_model(model)
        RUNTIME_CONFIG["default_provider"] = provider
        RUNTIME_CONFIG["default_model"] = model
    elif "provider" in payload or "default_provider" in payload:
        RUNTIME_CONFIG["default_provider"] = provider
        if current_default_model() not in AI_PROVIDERS[provider]["models"]:
            RUNTIME_CONFIG["default_model"] = AI_PROVIDERS[provider]["default_model"]

    runtime_keys = RUNTIME_CONFIG.setdefault("api_keys", {"zhipu": "", "deepseek": ""})
    for provider_id in AI_PROVIDERS:
        key_name = f"{provider_id}_api_key"
        if key_name in payload:
            api_key = str(payload.get(key_name) or "").strip()
            if api_key:
                runtime_keys[provider_id] = api_key
    if "api_keys" in payload and isinstance(payload["api_keys"], dict):
        for pid, value in payload["api_keys"].items():
            if pid in AI_PROVIDERS and str(value or "").strip():
                runtime_keys[pid] = str(value).strip()
    if "api_key" in payload:
        api_key = str(payload.get("api_key") or "").strip()
        if api_key:
            runtime_keys[provider] = api_key
    clear_provider = payload.get("clear_provider")
    if clear_provider:
        runtime_keys[normalize_provider(clear_provider)] = ""
    elif payload.get("clear_api_key"):
        runtime_keys[provider] = ""
    return config_payload()
