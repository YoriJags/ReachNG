"""Unified customer dossier — one timeline across WhatsApp + email.

Given a phone OR an email, resolve the customer's *other* identifier via the
identity links (Phase 3), then merge their inbound history from both channels
into one time-ordered timeline. This is the visible payoff of the unified inbox:
the owner sees a single relationship, and EYO has context across both.

Best-effort + read-only. No PII in logs.
"""
from __future__ import annotations

from typing import Optional

import structlog

log = structlog.get_logger()


def _db():
    from database import get_db
    return get_db()


def _ts(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def dossier_for(client_name: str, *, phone: Optional[str] = None,
                email: Optional[str] = None) -> dict:
    """Resolve the unified customer and return a merged WhatsApp+email timeline."""
    from services.identity import (
        normalize_phone, normalize_email,
        linked_email_for_phone, linked_phone_for_email,
    )
    p = normalize_phone(phone) if phone else None
    e = normalize_email(email) if email else None
    # Fill in the missing half from the identity graph.
    if client_name and p and not e:
        e = linked_email_for_phone(client_name, p)
    if client_name and e and not p:
        p = linked_phone_for_email(client_name, e)

    events: list[dict] = []
    try:
        db = _db()
        if e:
            for m in db["email_messages"].find(
                {"client_name": client_name, "from_email": e},
                {"direction": 1, "subject": 1, "body": 1, "received_at": 1},
            ).sort("received_at", 1).limit(100):
                events.append({
                    "channel":   "email",
                    "direction": m.get("direction") or "inbound",
                    "subject":   m.get("subject"),
                    "text":      (m.get("body") or "")[:500],
                    "at":        _ts(m.get("received_at")),
                })
        if p:
            for m in db["inbound_messages"].find(
                {"client_name": client_name, "sender_phone": {"$regex": p[-10:]}},
                {"body": 1, "received_at": 1},
            ).sort("received_at", 1).limit(100):
                events.append({
                    "channel":   "whatsapp",
                    "direction": "inbound",
                    "text":      (m.get("body") or "")[:500],
                    "at":        _ts(m.get("received_at")),
                })
    except Exception as ex:
        log.warning("dossier_gather_failed", error=str(ex))

    events.sort(key=lambda x: (x.get("at") or ""))
    channels = sorted({ev["channel"] for ev in events})
    return {
        "client":   client_name,
        "phone":    p,
        "email":    e,
        "linked":   bool(p and e),
        "channels": channels,
        "events":   events,
    }
