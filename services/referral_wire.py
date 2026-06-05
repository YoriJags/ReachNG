"""Referral wiring (EYO invention #5, live path).

When an outcome resolves to a genuine close (paid / booked / deposit), and the
client has the `referral` flag on, EYO drafts a warm referral ask for the owner
to approve. Routes through HITL like everything else — nothing sends itself.

The decision/copy/code live in the tested pure core (services/referral.py); this
module is the thin, NON-BLOCKING adapter: it reads the flag, dedupes (never ask
the same contact twice), drafts, and queues. Any failure is swallowed so it can
never break outcome tagging or a customer reply.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from services.eyo_flags import eyo_enabled
from services.referral import should_ask_referral, mint_referral_code, referral_ask_text

log = structlog.get_logger()

# Only ask after a real close, not a soft "interested"/"yes" — asking too early
# reads as pushy. These are the win_signals that mean money or a firm commitment.
_STRONG_WINS = {"paid", "booked", "deposit_made", "deposit", "closed"}


def _asks_col():
    from database import get_db
    return get_db()["referral_asks"]


def _already_asked(client_name: str, contact_phone: str) -> bool:
    try:
        return _asks_col().find_one(
            {"client_name": client_name, "contact_phone": contact_phone}, {"_id": 1}
        ) is not None
    except Exception:
        # Fail-safe toward "already asked" so a read error never double-pesters.
        return True


def _record_ask(client_name: str, contact_phone: str, code: str) -> None:
    try:
        _asks_col().insert_one({
            "client_name":   client_name,
            "contact_phone": contact_phone,
            "code":          code,
            "asked_at":      datetime.now(timezone.utc),
        })
    except Exception as e:
        log.warning("referral_ask_record_failed", error=str(e))


def maybe_ask_referral(
    *,
    client_name: Optional[str],
    contact_phone: Optional[str],
    contact_name: Optional[str] = None,
    win_signal: Optional[str] = None,
    agent_name: str = "EYO",
) -> bool:
    """Best-effort: queue a HITL referral-ask draft after a genuine win.

    Returns True iff a draft was queued. Never raises.
    """
    try:
        if not client_name or not contact_phone:
            return False
        if (win_signal or "").lower() not in _STRONG_WINS:
            return False
        if not eyo_enabled(client_name, "referral"):
            return False

        already = _already_asked(client_name, contact_phone)
        if not should_ask_referral(outcome_status="win", already_asked=already):
            return False

        code = mint_referral_code(client_name, contact_phone)
        message = referral_ask_text(contact_name, agent_name=agent_name)

        from tools.hitl import queue_draft
        queue_draft(
            contact_id=contact_phone,
            contact_name=contact_name or "",
            vertical="general",
            channel="whatsapp",
            message=message,
            phone=contact_phone,
            client_name=client_name,
            source="referral",   # transactional — skips the prospecting brief gate
        )
        _record_ask(client_name, contact_phone, code)
        log.info("referral_ask_queued", client_name=client_name, code=code)
        return True
    except Exception as e:
        log.warning("referral_ask_failed", error=str(e))
        return False
