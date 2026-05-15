"""
Waitlist — pre-launch capture for Lagos SMEs interested in ReachNG.

Why this exists
---------------
Before we open the floodgates, we want to:
  1. Capture intent + segment it (vertical, business size, location)
  2. Hand-onboard the first batch so they get wow-quality service
  3. Show scarcity ("not for everyone") — premium positioning lever
  4. Buy time to harden Usage Quotas + Admin Billing before scale

Each entry gets a position number. The hero CTA + /waitlist page both
funnel here. Admin can later invite people in batches via the dashboard.

Schema
------
waitlist:
  _id, position (int, monotonic), name, business_name, vertical, phone,
  email, city, brief_pain (free text), source (utm or "direct"),
  created_at, invited_at?, signed_up_at?
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Collection ───────────────────────────────────────────────────────────────

def _col():
    return get_db()["waitlist"]


def ensure_waitlist_indexes() -> None:
    col = _col()
    col.create_index([("position", ASCENDING)], unique=True)
    col.create_index([("phone", ASCENDING)], unique=True, sparse=True)
    col.create_index([("email", ASCENDING)], sparse=True)
    col.create_index([("created_at", DESCENDING)])
    col.create_index([("vertical", ASCENDING)])


# ─── Helpers ─────────────────────────────────────────────────────────────────

PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{7,17}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    # Nigerian local-format → international: 0816... → 234816...
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    return digits


def _next_position() -> int:
    last = _col().find_one(sort=[("position", -1)], projection={"position": 1})
    return ((last or {}).get("position", 0) or 0) + 1


# ─── Public: add ──────────────────────────────────────────────────────────────

def add_to_waitlist(
    *,
    name: str,
    business_name: str,
    vertical: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    city: Optional[str] = None,
    brief_pain: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    """Insert a new waitlist entry. Returns the persisted doc + position.

    Validates:
      - At least one of phone/email must be present
      - Phone matches loose international regex (then normalised to digits only)
      - Email looks like an email
      - name + business_name + vertical required
    Raises ValueError on validation failure.
    """
    name = (name or "").strip()
    business_name = (business_name or "").strip()
    vertical = (vertical or "").strip().lower()
    if not name:
        raise ValueError("name is required")
    if not business_name:
        raise ValueError("business_name is required")
    if not vertical:
        raise ValueError("vertical is required")

    phone_norm = _normalise_phone(phone)
    email = (email or "").strip().lower() or None
    if email and not EMAIL_RE.match(email):
        raise ValueError("email looks invalid")
    if not phone_norm and not email:
        raise ValueError("provide either a WhatsApp number or an email")

    # Already on the list? Return the existing entry instead of throwing.
    if phone_norm:
        existing = _col().find_one({"phone": phone_norm})
        if existing:
            existing["_id"] = str(existing["_id"])
            return existing
    if email:
        existing = _col().find_one({"email": email})
        if existing:
            existing["_id"] = str(existing["_id"])
            return existing

    now = datetime.now(timezone.utc)
    position = _next_position()
    doc = {
        "position":      position,
        "name":          name[:80],
        "business_name": business_name[:120],
        "vertical":      vertical[:32],
        "phone":         phone_norm,
        "email":         email,
        "city":          (city or "").strip()[:60] or None,
        "brief_pain":    (brief_pain or "").strip()[:600] or None,
        "source":        (source or "direct").strip()[:32],
        "created_at":    now,
        "invited_at":    None,
        "signed_up_at":  None,
    }
    _col().insert_one(doc)
    log.info("waitlist_joined", position=position, business=business_name, vertical=vertical)
    doc["_id"] = str(doc.pop("_id", "")) if "_id" in doc else ""
    return doc


# ─── Public: stats ────────────────────────────────────────────────────────────

def waitlist_total() -> int:
    return _col().count_documents({})


def waitlist_public_counter() -> dict:
    """Light-weight public counter for the landing page social-proof tile.
    Returns total + a comma-separated short list of verticals represented."""
    total = waitlist_total()
    by_vertical = list(_col().aggregate([
        {"$group": {"_id": "$vertical", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 5},
    ]))
    return {
        "total":       total,
        "top_verticals": [{"vertical": r["_id"], "count": r["n"]} for r in by_vertical if r.get("_id")],
    }


# ─── Admin: list + invite ─────────────────────────────────────────────────────

def list_waitlist(*, limit: int = 200, vertical: Optional[str] = None,
                   only_uninvited: bool = False) -> list[dict]:
    q: dict = {}
    if vertical:
        q["vertical"] = vertical.lower()
    if only_uninvited:
        q["invited_at"] = None
    rows = list(_col().find(q).sort("position", 1).limit(min(500, limit)))
    for r in rows:
        r["_id"] = str(r["_id"])
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        if isinstance(r.get("invited_at"), datetime):
            r["invited_at"] = r["invited_at"].isoformat()
    return rows


def mark_invited(position: int) -> bool:
    res = _col().update_one(
        {"position": position},
        {"$set": {"invited_at": datetime.now(timezone.utc)}},
    )
    return res.modified_count > 0
