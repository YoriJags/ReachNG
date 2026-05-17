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
    # Drop legacy sparse phone index if present — sparse doesn't skip explicit
    # nulls, which crashed email-only signups with DuplicateKeyError.
    try:
        existing = col.index_information()
        if "phone_1" in existing and existing["phone_1"].get("sparse"):
            col.drop_index("phone_1")
    except Exception:
        pass
    col.create_index(
        [("phone", ASCENDING)],
        unique=True,
        name="phone_1",
        partialFilterExpression={"phone": {"$type": "string"}},
    )
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

    # ── Confirmations (best-effort, non-blocking) ────────────────────────────
    # Fire WhatsApp + email in parallel. Email is the system of record (visible
    # to the signup days later); WhatsApp gives instant reassurance. Both fire
    # if both contact channels were given so the signup has a written trail.
    if phone_norm:
        _send_waitlist_confirmation_async(
            phone=phone_norm,
            name=name,
            position=position,
            business_name=business_name,
        )
    if email:
        _send_waitlist_email_async(
            to_email=email,
            name=name,
            position=position,
            business_name=business_name,
        )
    return doc


# ─── Confirmation send ───────────────────────────────────────────────────────

def _compose_confirmation(name: str, position: int, business_name: str) -> str:
    """Warm, brand-voiced confirmation. Reads like EYO from ReachNG, not a bot."""
    first = (name or "").split()[0] if name else ""
    greet = f"Hi {first}," if first else "Hi,"
    return (
        f"{greet} EYO here from ReachNG.\n\n"
        f"You're #{position} on the waitlist — saved you a spot for {business_name}.\n\n"
        f"We're onboarding Lagos SMEs in small batches so the first 30 days feel hand-built (because they are). "
        f"I'll WhatsApp you the moment your spot opens, with a quick onboarding link.\n\n"
        f"While you wait, the live demo runs the same engine on real Lagos sample data: "
        f"www.reachng.ng/portal/demo\n\n"
        f"Any quick question — just reply here."
    )


def _send_waitlist_confirmation_async(*, phone: str, name: str, position: int, business_name: str) -> None:
    """Schedule the confirmation send without blocking the HTTP response.
    Never raises — confirmation failure must not break waitlist signup.
    """
    try:
        from tools.outreach import send_whatsapp_for_client
        import asyncio

        text = _compose_confirmation(name=name, position=position, business_name=business_name)

        async def _fire():
            try:
                await send_whatsapp_for_client(phone=phone, message=text, client_doc=None)
                log.info("waitlist_confirmation_sent", position=position)
            except Exception as e:
                log.warning("waitlist_confirmation_send_failed", position=position, error=str(e))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_fire())
            else:
                loop.run_until_complete(_fire())
        except RuntimeError:
            asyncio.run(_fire())
    except Exception as e:
        log.warning("waitlist_confirmation_dispatch_failed", error=str(e))


# ─── Email confirmation (parallel channel to WhatsApp) ───────────────────────

def _compose_confirmation_email(name: str, position: int, business_name: str) -> tuple[str, str]:
    """Returns (subject, body) for the waitlist confirmation email.

    Slightly longer than the WhatsApp version because email is a permanent
    record — the recipient may re-read it days later when their spot opens.
    """
    first = (name or "").split()[0] if name else ""
    greet = f"Hi {first}," if first else "Hi,"
    subject = f"You're #{position} on the ReachNG waitlist"
    body = (
        f"{greet}\n\n"
        f"EYO here from ReachNG. You're #{position} on the waitlist — saved you a spot for {business_name}.\n\n"
        f"What happens next:\n"
        f"  1. We onboard Lagos businesses in small batches so the first 30 days feel hand-built (because they are).\n"
        f"  2. When your spot opens, I'll WhatsApp + email you a quick onboarding link.\n"
        f"  3. First call is a 30-min pairing where we connect your WhatsApp number — you're up and running by the end of it.\n\n"
        f"While you wait, the live demo runs the engine on realistic Lagos sample data: https://www.reachng.ng/portal/demo\n\n"
        f"Any quick question — just reply to this email.\n\n"
        f"— EYO\n"
        f"   On behalf of the team at ReachNG\n"
        f"   hello@reachng.ng · Lagos"
    )
    return subject, body


def _send_waitlist_email_async(*, to_email: str, name: str, position: int, business_name: str) -> None:
    """Fire-and-forget email confirmation. Never raises — confirmation failure
    must not break waitlist signup."""
    try:
        from tools.outreach import send_email
        import asyncio

        subject, body = _compose_confirmation_email(name=name, position=position, business_name=business_name)

        async def _fire():
            try:
                await send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    reply_to="hello@reachng.ng",
                    force_smtp=True,
                )
                log.info("waitlist_email_sent", position=position)
            except Exception as e:
                log.warning("waitlist_email_send_failed", position=position, error=str(e))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_fire())
            else:
                loop.run_until_complete(_fire())
        except RuntimeError:
            asyncio.run(_fire())
    except Exception as e:
        log.warning("waitlist_email_dispatch_failed", error=str(e))


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
