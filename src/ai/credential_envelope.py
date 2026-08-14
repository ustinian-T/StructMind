"""Decrypt short-lived per-user credentials delivered by the uniCloud Agent proxy."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialEnvelopeError(RuntimeError):
    """Public-safe Agent credential error."""

    code = "AI_CREDENTIAL_INVALID"


PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "minimax": {
        "protocol": "anthropic", "base_url": "https://api.minimaxi.com/anthropic",
        "models": {"MiniMax-M3[1M]"},
    },
    "deepseek": {
        "protocol": "anthropic", "base_url": "https://api.deepseek.com/anthropic",
        "models": {"deepseek-v4-flash", "deepseek-v4-pro[1m]"},
    },
    "volcengine": {
        "protocol": "anthropic", "base_url": "https://ark.cn-beijing.volces.com/api/plan",
        "models": {"ark-code-latest"},
    },
    "stepfun": {
        "protocol": "openai", "base_url": "https://api.stepfun.com/step_plan/v1",
        "models": {"step-router-v1"},
    },
}


@dataclass(frozen=True)
class EphemeralCredential:
    provider_id: str
    model_id: str
    api_key: str
    protocol: str
    base_url: str
    external_user_id: str
    expires_at: int
    nonce: str


_NONCES: dict[str, int] = {}
_NONCE_LOCK = Lock()


def _decode_transport_key() -> bytes:
    try:
        key = base64.b64decode(os.environ.get("SM_AGENT_CREDENTIAL_KEY", ""), validate=True)
    except Exception as exc:
        raise CredentialEnvelopeError("Agent 凭据密钥配置无效。") from exc
    if len(key) != 32:
        raise CredentialEnvelopeError("Agent 凭据密钥配置无效。")
    return key


def _reject_replay(nonce: str, expires_at: int, now_ms: int) -> None:
    if not nonce:
        raise CredentialEnvelopeError("Agent 凭据缺少随机标识。")
    with _NONCE_LOCK:
        expired = [value for value, expiry in _NONCES.items() if expiry < now_ms]
        for value in expired:
            _NONCES.pop(value, None)
        if nonce in _NONCES:
            raise CredentialEnvelopeError("Agent 凭据已被使用。")
        _NONCES[nonce] = expires_at


def decrypt_agent_envelope(
    envelope: dict[str, Any], *, expected_user_id: str, now_ms: int | None = None,
) -> EphemeralCredential:
    """Decrypt, validate and consume a one-time credential envelope."""

    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    try:
        if int(envelope.get("version", 0)) != 1:
            raise ValueError("version")
        iv = base64.b64decode(str(envelope["iv"]), validate=True)
        ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
        tag = base64.b64decode(str(envelope["auth_tag"]), validate=True)
        plaintext = AESGCM(_decode_transport_key()).decrypt(
            iv, ciphertext + tag, b"structmind-agent-envelope:v1",
        )
        payload = json.loads(plaintext.decode("utf-8"))
    except CredentialEnvelopeError:
        raise
    except Exception as exc:
        raise CredentialEnvelopeError("Agent 凭据无效或已损坏。") from exc

    provider_id = str(payload.get("provider_id") or "")
    model_id = str(payload.get("model_id") or "")
    user_id = str(payload.get("external_user_id") or "")
    api_key = str(payload.get("api_key") or "").strip()
    nonce = str(payload.get("nonce") or "")
    issued_at = int(payload.get("issued_at") or 0)
    expires_at = int(payload.get("expires_at") or 0)

    if expires_at - issued_at <= 0 or expires_at - issued_at > 60_000:
        raise CredentialEnvelopeError("Agent 凭据有效期无效。")
    if now_ms < issued_at or now_ms > expires_at:
        raise CredentialEnvelopeError("Agent 凭据已过期或尚未生效。")
    if user_id != str(expected_user_id):
        raise CredentialEnvelopeError("Agent 凭据用户不匹配。")
    provider = PROVIDER_CONFIGS.get(provider_id)
    if not provider or model_id not in provider["models"]:
        raise CredentialEnvelopeError("Agent 凭据模型不在允许列表中。")
    if not api_key:
        raise CredentialEnvelopeError("Agent 凭据缺少 API Key。")

    _reject_replay(nonce, expires_at, now_ms)
    return EphemeralCredential(
        provider_id=provider_id,
        model_id=model_id,
        api_key=api_key,
        protocol=str(provider["protocol"]),
        base_url=str(provider["base_url"]),
        external_user_id=user_id,
        expires_at=expires_at,
        nonce=nonce,
    )
