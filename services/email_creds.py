"""Per-client email credentials (IMAP/SMTP) — encrypted at rest.

Lets EYO connect to a client's mailbox DIRECTLY over IMAP/SMTP — any provider
(Gmail app-password, Zoho, cPanel, Go54...), with NO dependency on Unipile and NO
OAuth-verification gate.

Security: the mailbox password is encrypted with Fernet (EMAIL_CRED_KEY). If the
key — or the cryptography lib — is absent, we REFUSE to store the credential
rather than ever persisting a plaintext password. `cryptography` is imported
lazily so its absence can never break app boot, only this feature.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
        log.warning("email_cred_fernet_unavailable", error=str(e))
        return None


def encryption_available() -> bool:
    return _fernet() is not None


def _enc(plain: str) -> Optional[str]:
    f = _fernet()
    return f.encrypt(plain.encode()).decode() if (f and plain) else None


def _dec(token: str) -> Optional[str]:
    f = _fernet()
    if not (f and token):
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        return None


def _clients():
    from database import get_db
    return get_db()["clients"]


def set_email_credentials(client_name: str, *, imap_host: str, imap_port: int,
                          smtp_host: str, smtp_port: int, username: str,
                          password: str, use_ssl: bool = True) -> bool:
    """Store a client's IMAP/SMTP credentials (password encrypted). Raises if no
    encryption key is configured — never stores a plaintext password."""
    if not encryption_available():
        raise RuntimeError(
            "EMAIL_CRED_KEY not configured — refusing to store an email password "
            "without encryption")
    enc = _enc(password)
    if not enc:
        return False
    res = _clients().update_one(
        {"name": client_name},
        {"$set": {
            "email_provider":      "imap",
            "email_imap":          {"host": imap_host, "port": int(imap_port),
                                    "use_ssl": bool(use_ssl)},
            "email_smtp":          {"host": smtp_host, "port": int(smtp_port),
                                    "use_ssl": bool(use_ssl)},
            "email_username":      username,
            "email_account_id":    username,      # so handle_inbound_email can match
            "email_password_enc":  enc,
            "email_connected_at":  datetime.now(timezone.utc),
        }},
    )
    return bool(res.matched_count)


def get_email_credentials(client_doc: Optional[dict]) -> Optional[dict]:
    """Decrypted IMAP/SMTP creds for an IMAP-provider client, or None."""
    if not client_doc or client_doc.get("email_provider") != "imap":
        return None
    pw = _dec(client_doc.get("email_password_enc"))
    if not pw:
        return None
    return {
        "imap":     client_doc.get("email_imap") or {},
        "smtp":     client_doc.get("email_smtp") or {},
        "username": client_doc.get("email_username"),
        "password": pw,
    }
