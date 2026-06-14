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

from services.core.config import get_settings

_DEV_PASSPHRASE = b"glowsky-dev-secret-do-not-use-in-production"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = get_settings().secret_key
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
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
