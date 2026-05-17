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
    # Pilot-application qualifying fields (2026-05-17 — see Codex landing audit)
    enquiry_volume: Optional[str] = None,           # <20 | 20-100 | 100+
    avg_deal_value: Optional[str] = None,           # <50k | 50k-500k | 500k-5M | 5M+
    top_pains: Optional[list] = None,               # multi: slow_replies, missed_followups, voice_notes, deposit_chase, unqualified_leads
    trust_ai_draft: Optional[str] = None,           # yes | maybe | no
    sample_customer_message: Optional[str] = None,  # the gold field — real customer enquiry text
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

    # Already on the list? Re-fire the confirmation(s) and return the existing
    # entry. Resending on duplicate submit is intentional: the user clearly
    # wants a reminder of their position, and it makes the system observable
    # in logs during testing.
    def _resend_for(existing: dict) -> dict:
        existing_id = str(existing.get("_id", ""))
        existing["_id"] = existing_id
        pos = int(existing.get("position") or 0)
        biz = existing.get("business_name") or business_name
        nm  = existing.get("name") or name
        ph  = existing.get("phone")
        em  = existing.get("email")
        if ph:
            _send_waitlist_confirmation_async(phone=ph, name=nm, position=pos, business_name=biz)
        if em:
            _send_waitlist_email_async(to_email=em, name=nm, position=pos, business_name=biz)
        log.info("waitlist_resent", position=pos)
        return existing

    if phone_norm:
        existing = _col().find_one({"phone": phone_norm})
        if existing:
            return _resend_for(existing)
    if email:
        existing = _col().find_one({"email": email})
        if existing:
            return _resend_for(existing)

    now = datetime.now(timezone.utc)
    position = _next_position()

    # Sanitise qualifying inputs against fixed vocabularies
    _vol_allowed = {"<20", "20-100", "100+"}
    _val_allowed = {"<50k", "50k-500k", "500k-5M", "5M+"}
    _pain_allowed = {"slow_replies", "missed_followups", "voice_notes", "deposit_chase", "unqualified_leads", "after_hours"}
    _trust_allowed = {"yes", "maybe", "no"}
    vol = (enquiry_volume or "").strip() if (enquiry_volume or "").strip() in _vol_allowed else None
    val = (avg_deal_value or "").strip() if (avg_deal_value or "").strip() in _val_allowed else None
    pains_clean = [p for p in (top_pains or []) if isinstance(p, str) and p in _pain_allowed][:8]
    trust = (trust_ai_draft or "").strip().lower() if (trust_ai_draft or "").strip().lower() in _trust_allowed else None
    sample = (sample_customer_message or "").strip()[:1200] or None

    # Internal triage status — computed from the qualifying signal.
    # Hidden from the public form (which just says "early access").
    # Admin dashboard surfaces this so we pick the right batch to onboard.
    high_value   = val in {"500k-5M", "5M+"}
    mid_value    = val == "50k-500k"
    high_volume  = vol in {"20-100", "100+"}
    trust_ok     = trust in {"yes", "maybe"}
    has_sample   = bool(sample)
    if high_value and high_volume and trust_ok and has_sample:
        triage = "priority_pilot"
    elif high_value and (high_volume or trust_ok):
        triage = "pilot_candidate"
    elif (high_value or (mid_value and high_volume)) or trust_ok:
        triage = "qualified"
    else:
        triage = "curious"

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
        # Pilot-application signal fields (collected softly under "help us prioritise")
        "enquiry_volume":          vol,
        "avg_deal_value":          val,
        "top_pains":               pains_clean or None,
        "trust_ai_draft":          trust,
        "sample_customer_message": sample,
        # Internal triage — never exposed publicly
        "triage":         triage,
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

def _compose_confirmation_email(name: str, position: int, business_name: str) -> tuple[str, str, str]:
    """Returns (subject, text, html) for the waitlist confirmation email.

    HTML version uses ReachNG's brand palette (cream bg, serif headers,
    burnt-sienna accents). Plain text version is included for clients
    that don't render HTML.
    """
    first = (name or "").split()[0] if name else ""
    greet = f"Hi {first}," if first else "Hi,"
    subject = f"You're on the ReachNG early access list"

    text = (
        f"{greet}\n\n"
        f"EYO here from ReachNG. Got you on the early access list for {business_name}.\n\n"
        f"What happens next:\n"
        f"  1. We're onboarding Lagos businesses in small batches so the first 30 days feel hand-built.\n"
        f"  2. Based on your answers, we may invite you into one of the first pilot batches. If so, I'll WhatsApp you within 24-48 hours with a tailored demo — how EYO would reply to your actual enquiries.\n"
        f"  3. First call is a 30-min pairing where we connect your WhatsApp number — you're live by the end of it.\n\n"
        f"While you wait, the engine runs on realistic Lagos sample data: https://www.reachng.ng/portal/demo\n\n"
        f"Any quick question — just reply to this email.\n\n"
        f"— EYO\n"
        f"   On behalf of the team at ReachNG\n"
        f"   hello@reachng.ng · Lagos"
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#FAF6EE;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1a1a1a;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#FAF6EE;padding:40px 16px;">
    <tr><td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#ffffff;border-radius:14px;border:1px solid #E8DEC8;overflow:hidden;">
        <!-- header -->
        <tr><td style="padding:32px 36px 20px 36px;border-bottom:1px solid #F1E8D4;">
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:600;color:#1a1a1a;letter-spacing:-0.5px;">
            Reach<span style="color:#B85C38;">NG</span>
          </div>
        </td></tr>

        <!-- early access banner -->
        <tr><td style="padding:32px 36px 8px 36px;">
          <div style="font-size:11px;letter-spacing:1.5px;font-weight:600;color:#7a6a3f;text-transform:uppercase;margin-bottom:8px;">You're in</div>
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:32px;font-weight:600;line-height:1.15;color:#1a1a1a;">
            You're on the early access list.
          </div>
        </td></tr>

        <!-- body -->
        <tr><td style="padding:24px 36px 8px 36px;font-size:15px;line-height:1.65;color:#3d3a33;">
          <p style="margin:0 0 16px 0;">{greet}</p>
          <p style="margin:0 0 16px 0;">EYO here from ReachNG. Got you on the list for <strong>{business_name}</strong>.</p>
          <p style="margin:24px 0 12px 0;font-weight:600;color:#1a1a1a;">What happens next</p>
          <ol style="margin:0 0 16px 0;padding-left:20px;">
            <li style="margin-bottom:8px;">We're onboarding Lagos businesses in small batches so the first 30 days feel hand-built.</li>
            <li style="margin-bottom:8px;">Based on your answers, we may invite you into one of the first pilot batches. If so, I'll WhatsApp you within 24-48 hours with a tailored demo.</li>
            <li style="margin-bottom:0;">First call is a 30-min pairing where we connect your WhatsApp number — you're live by the end of it.</li>
          </ol>
        </td></tr>

        <!-- CTA -->
        <tr><td style="padding:16px 36px 36px 36px;" align="left">
          <p style="margin:0 0 16px 0;font-size:15px;line-height:1.65;color:#3d3a33;">
            While you wait, see the engine on real Lagos sample data:
          </p>
          <a href="https://www.reachng.ng/portal/demo" style="display:inline-block;background:#1a1a1a;color:#FAF6EE;text-decoration:none;padding:12px 22px;border-radius:8px;font-size:14px;font-weight:600;letter-spacing:0.2px;">Open the live demo →</a>
        </td></tr>

        <!-- reply prompt -->
        <tr><td style="padding:0 36px 32px 36px;font-size:14px;line-height:1.6;color:#5a5a5a;border-top:1px solid #F1E8D4;padding-top:24px;">
          Any quick question — just reply to this email.
        </td></tr>

        <!-- signature -->
        <tr><td style="padding:0 36px 36px 36px;font-size:14px;line-height:1.6;color:#3d3a33;">
          — EYO<br>
          <span style="color:#7a6a3f;">On behalf of the team at ReachNG</span><br>
          <a href="mailto:hello@reachng.ng" style="color:#B85C38;text-decoration:none;">hello@reachng.ng</a> · Lagos
        </td></tr>
      </table>

      <!-- footer -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;margin-top:16px;">
        <tr><td style="text-align:center;font-size:12px;color:#9a8e6e;line-height:1.5;padding:8px 16px;">
          You're receiving this because you joined the ReachNG waitlist at reachng.ng.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

    return subject, text, html


def _send_waitlist_email_async(*, to_email: str, name: str, position: int, business_name: str) -> None:
    """Fire-and-forget email confirmation. Never raises — confirmation failure
    must not break waitlist signup."""
    try:
        from tools.outreach import send_email
        import asyncio

        subject, body, html = _compose_confirmation_email(name=name, position=position, business_name=business_name)

        async def _fire():
            try:
                await send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    html=html,
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
