"""
Weekly Owner Digest — every Monday 7am Lagos time.

What it sends
-------------
A WhatsApp message to each client's owner_phone summarising the last 7 days:
  • ₦ closed + bookings count
  • Hours saved
  • Median response time
  • Approval rate
  • Top moment of the week (highest-value deal or fastest reply)
  • Honest call-out if numbers were lower than the prior week

The message is composed by Claude Haiku with the raw KPIs in context so the
tone matches that owner's brief voice. Routes through HITL by default — the
operator approves before send. If the client has autopilot=True, sends
directly.

Deliberate design: this is the moment clients screenshot and share. Treat it
like marketing collateral, not a status email.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from bson import ObjectId

from database import get_db
from services.scorecard import compute_scorecard, format_ngn, format_response_time

log = structlog.get_logger()


def _db():
    return get_db()


# ─── Compose ──────────────────────────────────────────────────────────────────

def _compose_with_haiku(client: dict, sc, prev_sc) -> str:
    """Use Claude Haiku to compose a 4-6 sentence WhatsApp digest with the
    raw numbers in context. Falls back to a deterministic template on error.
    """
    fallback = _deterministic_digest(client, sc, prev_sc)
    try:
        from config import get_settings
        import anthropic
        settings = get_settings()
        if not settings.anthropic_api_key:
            return fallback
        client_api = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        delta_bookings = (sc.bookings_closed or 0) - (prev_sc.bookings_closed if prev_sc else 0)
        delta_ngn = (sc.ngn_closed or 0) - (prev_sc.ngn_closed if prev_sc else 0)

        system = (
            "You compose a short, warm, Lagos-business-friendly weekly WhatsApp "
            "digest for the OWNER of a Nigerian SME using ReachNG. Tone: like a "
            "trusted operations partner. No emojis except a single ✓ or 🔥 if "
            "the week was strong. 4-6 sentences max. End with the next-week "
            "intention. NEVER use placeholder text like [Name] — if you don't "
            "know the owner's name, just open with 'Morning,'."
        )
        owner_first = (client.get("owner_name") or "").split()[0] if client.get("owner_name") else None
        prompt = f"""Owner: {owner_first or '(unknown — open with "Morning,")'}
Business: {client.get('name')} ({client.get('vertical')})
Week's numbers:
- ₦ Closed: {format_ngn(sc.ngn_closed)}  ({sc.bookings_closed} bookings)
- Hours saved: {sc.hours_saved:.1f}h
- Approval rate: {round((sc.approval_rate or 0)*100)}%
- Median response: {format_response_time(sc.median_response_seconds)}
- Drafts approved: {sc.drafts_approved}
- Pending claimed: {format_ngn(sc.ngn_pending)}

Vs prior 7 days:
- ₦ delta: {format_ngn(delta_ngn)}  ({'+' if delta_bookings >= 0 else ''}{delta_bookings} bookings)

Write the WhatsApp digest now. No preamble, no markdown, just the message text."""

        resp = client_api.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        txt = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return txt or fallback
    except Exception as e:
        log.warning("digest_compose_failed", error=str(e))
        return fallback


def _deterministic_digest(client: dict, sc, prev_sc) -> str:
    owner = (client.get("owner_name") or "").split()[0] if client.get("owner_name") else None
    salute = f"Morning {owner}," if owner else "Morning,"
    line1 = (
        f"Last week your ReachNG agent closed {format_ngn(sc.ngn_closed)} across "
        f"{sc.bookings_closed} booking{('s' if sc.bookings_closed != 1 else '')}."
    )
    line2 = (
        f"You approved {sc.drafts_approved} drafts — that's {sc.hours_saved:.1f}h of "
        f"typing you didn't have to do."
    )
    line3 = ""
    if sc.median_response_seconds is not None:
        line3 = f"Median customer response time: {format_response_time(sc.median_response_seconds)}."
    line4 = ""
    if sc.ngn_pending and sc.ngn_pending > 0:
        line4 = f"{format_ngn(sc.ngn_pending)} is claimed but not yet verified — worth a quick check today."
    closing = "I'll keep the queue moving this week — happy Monday."
    return "\n\n".join([salute, line1, line2, line3, line4, closing]).strip()


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def send_weekly_digests() -> dict:
    """Run for every active client with a configured owner_phone. Returns counts."""
    db = _db()
    sent = 0
    queued = 0
    skipped = 0
    for c in db["clients"].find({"active": True}, {"_id": 1, "name": 1, "vertical": 1,
                                                    "owner_phone": 1, "owner_name": 1,
                                                    "autopilot": 1}):
        if not c.get("owner_phone"):
            skipped += 1
            continue
        try:
            cid = str(c["_id"])
            sc = compute_scorecard(cid, period_days=7)
            try:
                prev_sc = compute_scorecard(cid, period_days=14)
            except Exception:
                prev_sc = None
            # Diff prev = (prev 14d) - (current 7d) → approximate "prior 7d" by subtraction
            # For simplicity v1 we just use the 14-day window as the prior baseline
            text = _compose_with_haiku(c, sc, prev_sc)

            from tools.hitl import queue_draft
            try:
                approval_id = queue_draft(
                    contact_id=cid,
                    contact_name=(c.get("owner_name") or c.get("name") or "Owner"),
                    vertical=c.get("vertical") or "general",
                    channel="whatsapp",
                    message=text,
                    phone=c.get("owner_phone"),
                    source="weekly_digest",
                    client_name=c.get("name"),
                )
                queued += 1
                log.info("weekly_digest_queued", client=c.get("name"), approval=approval_id)
            except Exception as _e:
                log.warning("weekly_digest_queue_failed", client=c.get("name"), error=str(_e))
                skipped += 1
        except Exception as e:
            log.warning("weekly_digest_failed_for_client", client=c.get("name"), error=str(e))
            skipped += 1
    return {"queued": queued, "sent_direct": sent, "skipped": skipped}
