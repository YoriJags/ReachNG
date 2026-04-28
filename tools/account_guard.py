"""
Per-account guardrails for outbound prospecting.

Two concerns:
  1. Daily send caps — WhatsApp throttles aggressive accounts. Unipile starts
     getting flagged around 200/day per number; Meta Cloud API stretches to
     ~1000/day on a warmed sender. We default to 200/day (Unipile-safe).
  2. Opt-out rate spikes — if more than OPTOUT_RATE_THRESHOLD_PCT of a client's
     recent replies are STOP/UNSUBSCRIBE/REMOVE, auto-pause their outreach so
     a single bad list doesn't get the WhatsApp account suspended.

State is persisted on the client doc (`outreach_paused`, `outreach_paused_reason`,
`outreach_paused_at`). The clients endpoint surfaces this; admins flip it back.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import get_db
import structlog

log = structlog.get_logger()


# ─── Tunables (per-client overrides via clients.outreach_caps.*) ─────────────

DEFAULT_DAILY_CAP                  = 200    # outbound drafts per client per UTC day
OPTOUT_RATE_THRESHOLD_PCT          = 3.0    # auto-pause when >3% of recent replies opt out
OPTOUT_WINDOW_HOURS                = 24
OPTOUT_MIN_REPLIES_FOR_TRIGGER     = 30     # don't auto-pause off a tiny sample

# Sender warm-up — prevents Meta WhatsApp suspension on fresh accounts.
# A new client doc gets ramped over the first 7 days unless they explicitly
# set outreach_warmup_skip=True (their number is already warm from prior use).
WARMUP_DAYS_TOTAL = 7
WARMUP_SCHEDULE = [
    # (days_since_start_inclusive, daily_cap_during_this_phase)
    (3, 50),    # days 0-2: hard 50/day
    (7, 100),   # days 3-6: 100/day
]                # day 7+: configured cap (no ramp)


class OutreachCapExceeded(Exception):
    def __init__(self, client_name: str, sent_today: int, cap: int):
        self.client_name = client_name
        self.sent_today = sent_today
        self.cap = cap
        super().__init__(
            f"Daily outreach cap reached for '{client_name}' "
            f"({sent_today}/{cap} drafts queued today). Resumes at 00:00 UTC."
        )


class OutreachPaused(Exception):
    def __init__(self, client_name: str, reason: str):
        self.client_name = client_name
        self.reason = reason
        super().__init__(f"Outreach paused for '{client_name}': {reason}")


# ─── Public API ──────────────────────────────────────────────────────────────

def enforce_account_caps(*, client_name: str) -> None:
    """Call before every prospecting queue_draft to gate by cap + paused flag.

    Raises OutreachPaused or OutreachCapExceeded so callers can surface
    meaningful errors. Looks up the client doc once.

    Side-effect: records `outreach_started_at` on the client doc the first
    time a draft passes the gate, which seeds the warm-up window.
    """
    if not client_name:
        return

    client = _client_lookup(client_name)
    if not client:
        return  # no doc, nothing to enforce against

    # Manual + auto pause
    if client.get("outreach_paused"):
        raise OutreachPaused(
            client_name=client_name,
            reason=client.get("outreach_paused_reason") or "Outreach paused",
        )

    # Effective cap = configured cap, capped by warm-up phase if applicable.
    configured_cap = int((client.get("outreach_caps") or {}).get("daily") or DEFAULT_DAILY_CAP)
    warmup_phase = _warmup_phase(client)
    effective_cap = min(configured_cap, warmup_phase["cap"]) if warmup_phase["active"] else configured_cap

    sent_today = _count_sent_today(client_name)
    if sent_today >= effective_cap:
        raise OutreachCapExceeded(
            client_name=client_name,
            sent_today=sent_today,
            cap=effective_cap,
        )

    # Seed outreach_started_at on first successful pass — drives the warm-up window.
    if not client.get("outreach_started_at") and not client.get("outreach_warmup_skip"):
        get_db()["clients"].update_one(
            {"_id": client["_id"]},
            {"$set": {"outreach_started_at": datetime.now(timezone.utc)}},
        )


def maybe_auto_pause_on_optout_spike(*, client_name: str) -> Optional[dict]:
    """Inspect recent replies for this client; if opt-out rate exceeds threshold,
    flip outreach_paused on the client doc and return the snapshot. Idempotent —
    re-calling while already paused returns None.

    Intended to be called from the reply router after each new reply is classified.
    """
    if not client_name:
        return None
    client = _client_lookup(client_name)
    if not client:
        return None
    if client.get("outreach_paused"):
        return None

    since = datetime.now(timezone.utc) - timedelta(hours=OPTOUT_WINDOW_HOURS)
    replies_col = get_db()["replies"]
    query = {"client_name": client_name, "received_at": {"$gte": since}}
    total = replies_col.count_documents(query)
    if total < OPTOUT_MIN_REPLIES_FOR_TRIGGER:
        return None
    optouts = replies_col.count_documents({**query, "intent": "opted_out"})
    rate = (optouts / total) * 100 if total else 0.0
    if rate < OPTOUT_RATE_THRESHOLD_PCT:
        return None

    reason = (
        f"Auto-paused: opt-out rate {rate:.1f}% over last {OPTOUT_WINDOW_HOURS}h "
        f"({optouts}/{total} replies). Review brief + list quality before resuming."
    )
    get_db()["clients"].update_one(
        {"_id": client["_id"]},
        {"$set": {
            "outreach_paused": True,
            "outreach_paused_reason": reason,
            "outreach_paused_at": datetime.now(timezone.utc),
        }},
    )
    log.warning("outreach_auto_paused", client=client_name, rate=rate, optouts=optouts, total=total)
    return {"paused": True, "rate": rate, "optouts": optouts, "total": total, "reason": reason}


def get_account_status(*, client_name: str) -> dict:
    """Snapshot for admin dashboard / portal banner."""
    client = _client_lookup(client_name) or {}
    configured_cap = int((client.get("outreach_caps") or {}).get("daily") or DEFAULT_DAILY_CAP)
    sent_today = _count_sent_today(client_name) if client_name else 0
    warmup = _warmup_phase(client)
    effective_cap = min(configured_cap, warmup["cap"]) if warmup["active"] else configured_cap
    return {
        "client_name": client_name,
        "outreach_paused": bool(client.get("outreach_paused")),
        "outreach_paused_reason": client.get("outreach_paused_reason"),
        "configured_cap": configured_cap,
        "daily_cap": effective_cap,
        "sent_today": sent_today,
        "remaining_today": max(0, effective_cap - sent_today),
        "warmup": warmup,
    }


def resume_outreach(*, client_name: str) -> bool:
    """Admin-only — flip outreach_paused off."""
    client = _client_lookup(client_name)
    if not client:
        return False
    get_db()["clients"].update_one(
        {"_id": client["_id"]},
        {"$set": {"outreach_paused": False, "outreach_resumed_at": datetime.now(timezone.utc)},
         "$unset": {"outreach_paused_reason": ""}},
    )
    return True


# ─── Internal ────────────────────────────────────────────────────────────────

def _client_lookup(client_name: str) -> Optional[dict]:
    return get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    )


def _warmup_phase(client: dict) -> dict:
    """Compute current warm-up phase for the client's WhatsApp sender.

    Returns: {active: bool, day: int, cap: int, days_total: int}
    Where:
      active=True  → cap should be enforced as a ceiling on the configured cap
      day          → days since outreach_started_at (0-indexed)
      cap          → daily cap during this phase
      days_total   → length of full warm-up window
    """
    if client.get("outreach_warmup_skip"):
        return {"active": False, "day": -1, "cap": DEFAULT_DAILY_CAP, "days_total": 0}

    started = client.get("outreach_started_at")
    if not started:
        # No drafts queued yet — first call to enforce_account_caps will seed it.
        # Treat as day 0 of warm-up so the very first day already has the 50/day cap.
        return {"active": True, "day": 0, "cap": WARMUP_SCHEDULE[0][1], "days_total": WARMUP_DAYS_TOTAL}

    if isinstance(started, str):
        try:
            started = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except Exception:
            return {"active": False, "day": -1, "cap": DEFAULT_DAILY_CAP, "days_total": 0}
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    days_since = (datetime.now(timezone.utc) - started).days
    if days_since >= WARMUP_DAYS_TOTAL:
        return {"active": False, "day": days_since, "cap": DEFAULT_DAILY_CAP, "days_total": WARMUP_DAYS_TOTAL}

    for upper_bound, cap in WARMUP_SCHEDULE:
        if days_since < upper_bound:
            return {"active": True, "day": days_since, "cap": cap, "days_total": WARMUP_DAYS_TOTAL}
    return {"active": False, "day": days_since, "cap": DEFAULT_DAILY_CAP, "days_total": WARMUP_DAYS_TOTAL}


def _count_sent_today(client_name: str) -> int:
    """Drafts queued today for this client. Treat queueing as the spend event —
    the moment we generate the draft we've already used a Claude call + a slot."""
    if not client_name:
        return 0
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return get_db()["pending_approvals"].count_documents({
        "client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"},
        "created_at": {"$gte": start_of_day},
    })
