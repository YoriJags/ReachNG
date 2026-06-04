"""
EYO Referral — word-of-mouth engine (invention #5).

Nigerian SME growth runs on word-of-mouth, but nobody systematises it on
WhatsApp. After a happy close, EYO asks for a referral/review at the right
moment, mints a trackable code, and works the referred contact when they arrive.
Closes the loop: money → reputation → more money.

Deterministic core (pure, no LLM): the decision (should we ask, and when), a
deterministic+idempotent referral code, and the ask copy. The trigger plumbing
(detecting the win via outcome_learning), HITL drafting, and attribution storage
are the wiring slice.
"""
from __future__ import annotations

import hashlib
from typing import Optional

# Don't pounce the instant a deal closes — let the good feeling settle.
DEFAULT_DELAY_HOURS = 4
_NEGATIVE = {"negative", "angry", "complaint", "disappointed", "frustrated"}


def should_ask_referral(
    *,
    outcome_status: str,
    sentiment: Optional[str] = None,
    already_asked: bool = False,
    deal_value_ngn: float = 0.0,
    min_value_ngn: float = 0.0,
) -> bool:
    """Only ask after a genuine, positive close we haven't already milked.

    - must be a win (closed deal)
    - never on negative sentiment (don't ask an unhappy customer to refer)
    - never twice
    - optionally gate on a minimum deal value
    """
    if already_asked:
        return False
    if (outcome_status or "").lower() != "win":
        return False
    if sentiment and sentiment.lower() in _NEGATIVE:
        return False
    if min_value_ngn and (deal_value_ngn or 0) < min_value_ngn:
        return False
    return True


def mint_referral_code(client_name: str, referrer_phone: str) -> str:
    """Deterministic + idempotent short code for a (client, referrer) pair —
    re-running never mints a duplicate."""
    raw = f"{(client_name or '').strip().lower()}:{(referrer_phone or '').strip()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6].upper()
    return f"REF{digest}"


def referral_ask_text(
    contact_name: Optional[str],
    *,
    agent_name: str = "EYO",
    reward: Optional[str] = None,
    link: Optional[str] = None,
) -> str:
    """Warm, low-pressure referral ask for the owner to approve (HITL)."""
    who = contact_name or "there"
    lines = [f"So glad you're happy, {who}! 🙌"]
    if reward:
        lines.append(f"Know someone who'd love this too? Send them my way and {reward}.")
    else:
        lines.append("If you know someone who'd love this too, send them my way — it means a lot.")
    if link:
        lines.append(f"Here's a link they can use: {link}")
    return " ".join(lines)
