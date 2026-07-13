"""Symmetric encryption for secrets at rest (BYO-LLM provider keys).

Provider API keys are stored as Fernet ciphertext, never plaintext — rows hold only the
encrypted token plus a masked hint for display (docs/07 §2). The key comes from
GLOWSKY_SECRET_KEY; with none set, a deterministic DEV key is derived so local dev works,
but that key is public-by-construction and must never be used in production.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from services.core.config import Settings, get_settings

_DEV_PASSPHRASE = b"glowsky-dev-secret-do-not-use-in-production"

# Environments where the deterministic in-source dev key is acceptable (local hacking / CI).
# Anything else is treated as production-grade and MUST supply its own GLOWSKY_SECRET_KEY.
_DEV_ENVIRONMENTS = frozenset({"dev", "development", "local", "test", "testing", "ci"})


class InsecureSecretKeyError(RuntimeError):
    """Raised when a non-dev environment would fall back to the public in-source dev key."""


def _secret_key_required(settings: Settings) -> bool:
    return (settings.environment or "").strip().lower() not in _DEV_ENVIRONMENTS


def validate_secret_config(settings: Settings | None = None) -> None:
    """Fail-fast guard: in any non-dev environment a real GLOWSKY_SECRET_KEY must be set.

    Called at application startup (see apps/api/main.py lifespan). Without this, a self-hoster
    who forgets to set GLOWSKY_SECRET_KEY silently encrypts every stored BYO-LLM credential
    (customers' own Anthropic/OpenAI/Groq keys — their money) under a key that is published in
    this open-source repo and trivially reversible. We refuse to boot rather than offer that.
    """
    settings = settings or get_settings()
    if _secret_key_required(settings) and not settings.secret_key:
        raise InsecureSecretKeyError(
            f"GLOWSKY_SECRET_KEY must be set when GLOWSKY_ENVIRONMENT={settings.environment!r}: "
            "the built-in dev key is public-by-construction and would leave stored BYO-LLM "
            "credentials trivially decryptable. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        )


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.secret_key
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Fail closed even if startup validation was skipped (e.g. crypto used outside the API
    # process): never silently derive the public dev key in a production-grade environment.
    if _secret_key_required(settings):
        validate_secret_config(settings)
    # Dev fallback: a fixed, deterministic key. Encryption is real but the key is in
    # source, so this protects against casual DB inspection only — set GLOWSKY_SECRET_KEY
    # in any shared/production environment.
    derived = base64.urlsafe_b64encode(hashlib.sha256(_DEV_PASSPHRASE).digest())
    return Fernet(derived)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # wrong key / corrupted ciphertext
        raise ValueError("could not decrypt secret (wrong GLOWSKY_SECRET_KEY?)") from exc


def mask(secret: str) -> str:
    """A display hint that reveals neither the key nor its length, e.g. 'sk-…AB12'."""
    if len(secret) <= 6:
        return "…"
    return f"{secret[:3]}…{secret[-4:]}"
