"""
Email cadence rules for SDR outreach.

Prevents the same business email from being hit twice in a short window
across overlapping campaigns. Without this, a Lagos restaurant that
appears in both the "hospitality VI" run and the "premium dining
Ikoyi" run would get two emails the same day — bad signal for them,
worse for our sender-domain reputation.

Rule:
  If we've ALREADY queued or sent an email outreach to this address
  within the last EMAIL_COOLDOWN_DAYS (default 14), skip the new draft.

Implementation:
  Queries the existing `approvals` collection — every draft (pending,
  approved, sent) has email + channel + created_at. No new schema.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from config import get_settings
from database import get_db

log = structlog.get_logger()


def _approvals():
    return get_db()["approvals"]


def _cooldown_days() -> int:
    settings = get_settings()
    return int(getattr(settings, "email_cooldown_days", 14) or 14)


def was_recently_emailed(email: Optional[str], *, days: Optional[int] = None) -> Optional[dict]:
    """Return the most recent draft for this email in the cooldown window,
    or None if the address is clear to queue.

    Returns a dict with the matching draft's basic fields for logging.
    """
    if not email:
        return None
    cooldown = days if days is not None else _cooldown_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown)
    doc = _approvals().find_one(
        {
            "email":      email.strip().lower(),
            "channel":    "email",
            "created_at": {"$gte": cutoff},
        },
        sort=[("created_at", -1)],
        projection={"created_at": 1, "status": 1, "client_name": 1, "vertical": 1},
    )
    if not doc:
        return None
    return {
        "last_at":     doc.get("created_at"),
        "last_status": doc.get("status"),
        "client":      doc.get("client_name"),
        "vertical":    doc.get("vertical"),
    }


def should_skip_email(email: Optional[str], *, days: Optional[int] = None) -> dict:
    """Higher-level wrapper. Returns:
        {"skip": bool, "reason": str|None, "last_at": datetime|None, "cooldown_days": int}
    Use this from campaign loops so the skip event is observable.
    """
    cooldown = days if days is not None else _cooldown_days()
    hit = was_recently_emailed(email, days=cooldown)
    if not hit:
        return {"skip": False, "reason": None, "last_at": None, "cooldown_days": cooldown}
    return {
        "skip":           True,
        "reason":         "cooldown",
        "last_at":        hit.get("last_at"),
        "cooldown_days":  cooldown,
        "last_status":    hit.get("last_status"),
        "last_client":    hit.get("client"),
    }


def ensure_email_cadence_indexes() -> None:
    """The approvals collection already has good indexes for (created_at).
    Add a compound index on (email, channel, created_at) for the cadence query."""
    _approvals().create_index(
        [("email", 1), ("channel", 1), ("created_at", -1)],
        name="email_cadence_lookup",
        sparse=True,
    )
