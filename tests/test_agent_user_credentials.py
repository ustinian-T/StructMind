import base64
import json

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.ai.credential_envelope import CredentialEnvelopeError, decrypt_agent_envelope


KEY_BYTES = bytes([9]) * 32
KEY_B64 = base64.b64encode(KEY_BYTES).decode("ascii")


def make_envelope(*, user_id="user-a", issued_at=1_000_000, expires_at=1_060_000, nonce="nonce-a"):
    payload = {
        "provider_id": "deepseek",
        "model_id": "deepseek-v4-flash",
        "api_key": "unit-test-secret",
        "external_user_id": user_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }
    iv = bytes(range(12))
    combined = AESGCM(KEY_BYTES).encrypt(
        iv,
        json.dumps(payload, separators=(",", ":")).encode(),
        b"structmind-agent-envelope:v1",
    )
    return {
        "version": 1,
        "iv": base64.b64encode(iv).decode(),
        "ciphertext": base64.b64encode(combined[:-16]).decode(),
        "auth_tag": base64.b64encode(combined[-16:]).decode(),
    }


def test_valid_envelope_returns_ephemeral_credential(monkeypatch):
    monkeypatch.setenv("SM_AGENT_CREDENTIAL_KEY", KEY_B64)
    credential = decrypt_agent_envelope(
        make_envelope(), expected_user_id="user-a", now_ms=1_030_000,
    )
    assert credential.provider_id == "deepseek"
    assert credential.model_id == "deepseek-v4-flash"
    assert credential.api_key == "unit-test-secret"


@pytest.mark.parametrize("kwargs", [
    {"expires_at": 1_060_001},
    {"expires_at": 999_999},
    {"user_id": "user-b"},
])
def test_invalid_ttl_expiry_or_user_is_rejected(monkeypatch, kwargs):
    monkeypatch.setenv("SM_AGENT_CREDENTIAL_KEY", KEY_B64)
    expected_user = "user-a"
    with pytest.raises(CredentialEnvelopeError):
        decrypt_agent_envelope(
            make_envelope(**kwargs), expected_user_id=expected_user, now_ms=1_030_000,
        )


def test_tampered_envelope_is_rejected(monkeypatch):
    monkeypatch.setenv("SM_AGENT_CREDENTIAL_KEY", KEY_B64)
    envelope = make_envelope()
    envelope["ciphertext"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(CredentialEnvelopeError):
        decrypt_agent_envelope(envelope, expected_user_id="user-a", now_ms=1_030_000)


def test_model_provider_mismatch_is_rejected(monkeypatch):
    monkeypatch.setenv("SM_AGENT_CREDENTIAL_KEY", KEY_B64)
    envelope = make_envelope()
    payload = {
        "provider_id": "stepfun", "model_id": "deepseek-v4-flash",
        "api_key": "unit-test-secret", "external_user_id": "user-a",
        "issued_at": 1_000_000, "expires_at": 1_060_000, "nonce": "nonce-mismatch",
    }
    iv = bytes(range(12))
    combined = AESGCM(KEY_BYTES).encrypt(
        iv, json.dumps(payload, separators=(",", ":")).encode(),
        b"structmind-agent-envelope:v1",
    )
    envelope.update(
        ciphertext=base64.b64encode(combined[:-16]).decode(),
        auth_tag=base64.b64encode(combined[-16:]).decode(),
    )
    with pytest.raises(CredentialEnvelopeError):
        decrypt_agent_envelope(envelope, expected_user_id="user-a", now_ms=1_030_000)
