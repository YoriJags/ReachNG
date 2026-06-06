"""Generic at-rest secret encryption (Fernet), keyed by EMAIL_CRED_KEY.

Used for any secret we must store + read back later (email passwords, Meta Page
access tokens). Same fail-safe rule everywhere: no key (or no cryptography lib)
=> `available()` is False and callers refuse to store, never plaintext.
cryptography is imported lazily so its absence can't break app boot.
"""
from __future__ import annotations

from typing import Optional

import structlog

from config import get_settings

log = structlog.get_logger()


def _fernet():
    key = get_settings().email_cred_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        log.warning("crypto_fernet_unavailable", error=str(e))
        return None


def available() -> bool:
    return _fernet() is not None


def encrypt(plain: str) -> Optional[str]:
    f = _fernet()
    return f.encrypt(plain.encode()).decode() if (f and plain) else None


def decrypt(token: str) -> Optional[str]:
    f = _fernet()
    if not (f and token):
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        return None
