"""Identity resolution — tie an email and a WhatsApp number to ONE customer.

This is the heart of the unified inbox: a customer who emails tunde@gmail.com and
also WhatsApps +2348031234567 should be a single relationship so EYO has full
context across both channels.

Confidence order, deterministic first:
  1. HARD signal  — the email body/signature carries a phone we already talk to,
     or a WhatsApp message carries an email. Strong enough to auto-link.
  2. OWNER one-tap — anything softer is a *suggestion* the owner confirms.
  (Fuzzy name matching is a later, lower-confidence layer.)

Stored per client. Pure helpers (extraction, normalization) + a small link store.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger()

_PHONE = re.compile(r"(?:\+?234|0)(?:[\s\-]?\d){9,10}")  # tolerates 0803 123 4567
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def normalize_phone(raw: str) -> Optional[str]:
    """Canonical Nigerian number as 234XXXXXXXXXX, or None if not a valid one."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("234"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return f"234{digits}" if len(digits) == 10 else None


def normalize_email(raw: str) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL.fullmatch(e) else None


def extract_phone_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = _PHONE.search(text)
    return normalize_phone(m.group(0)) if m else None


def extract_email_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = _EMAIL.search(text)
    return normalize_email(m.group(0)) if m else None


# ── Store ─────────────────────────────────────────────────────────────────────

def _links():
    from database import get_db
    return get_db()["customer_links"]


def _suggestions():
    from database import get_db
    return get_db()["link_suggestions"]


def ensure_identity_indexes() -> None:
    _links().create_index(
        [("client_name", 1), ("phone", 1), ("email", 1)], unique=True)
    _suggestions().create_index([("client_name", 1), ("status", 1)])


def link_identities(client_name: str, phone: str, email: str,
                    source: str = "hard_signal") -> bool:
    """Confirm a phone<->email link for a customer. Idempotent."""
    p, e = normalize_phone(phone), normalize_email(email)
    if not (client_name and p and e):
        return False
    _links().update_one(
        {"client_name": client_name, "phone": p, "email": e},
        {"$set": {"client_name": client_name, "phone": p, "email": e,
                  "source": source, "linked_at": datetime.now(timezone.utc)}},
        upsert=True)
    log.info("identity_linked", client=client_name, source=source)
    return True


def linked_email_for_phone(client_name: str, phone: str) -> Optional[str]:
    p = normalize_phone(phone)
    if not p:
        return None
    d = _links().find_one({"client_name": client_name, "phone": p}, {"email": 1})
    return d.get("email") if d else None


def linked_phone_for_email(client_name: str, email: str) -> Optional[str]:
    e = normalize_email(email)
    if not e:
        return None
    d = _links().find_one({"client_name": client_name, "email": e}, {"phone": 1})
    return d.get("phone") if d else None


def suggest_link(client_name: str, phone: str, email: str, reason: str = "") -> bool:
    """Record a pending link for the owner to confirm — unless it's already
    linked or already suggested."""
    p, e = normalize_phone(phone), normalize_email(email)
    if not (client_name and p and e):
        return False
    if _links().find_one({"client_name": client_name, "phone": p, "email": e}, {"_id": 1}):
        return False
    _suggestions().update_one(
        {"client_name": client_name, "phone": p, "email": e},
        {"$setOnInsert": {"client_name": client_name, "phone": p, "email": e,
                          "reason": reason, "status": "pending",
                          "created_at": datetime.now(timezone.utc)}},
        upsert=True)
    return True


def confirm_link(client_name: str, phone: str, email: str) -> bool:
    """Owner confirms a suggested link -> promote it to a confirmed link."""
    p, e = normalize_phone(phone), normalize_email(email)
    if not (client_name and p and e):
        return False
    _suggestions().update_one(
        {"client_name": client_name, "phone": p, "email": e},
        {"$set": {"status": "confirmed"}})
    return link_identities(client_name, p, e, source="owner_confirmed")


def reject_link(client_name: str, phone: str, email: str) -> bool:
    p, e = normalize_phone(phone), normalize_email(email)
    if not (client_name and p and e):
        return False
    res = _suggestions().update_one(
        {"client_name": client_name, "phone": p, "email": e},
        {"$set": {"status": "rejected"}})
    return bool(res.matched_count)


def pending_links(client_name: str) -> list[dict]:
    if not client_name:
        return []
    return list(_suggestions().find(
        {"client_name": client_name, "status": "pending"}, {"_id": 0}))
