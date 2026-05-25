"""
Inbound spike guard (WhatsApp ban defence layer).

If a single client's WhatsApp number gets a sudden burst of inbounds (viral
moment, IG mention, group blast, bot attack) and the drafter responds to
each one, Meta's spam classifier sees a high outbound rate from a freshly
paired number and disables the line.

This module sits in front of the auto-drafter. When inbound rate for a
client exceeds a threshold over a short window, we:
  1. Set `clients.spike_paused_until` for SPIKE_PAUSE_MINUTES
  2. Skip auto-draft for the duration (HITL queue still works manually)
  3. Fire client's `holding_message` to each new inbound during the pause
  4. WhatsApp the operator with one alert

Rate limit is per-client; no global throttle. Resolves itself on the wall
clock — no operator action required.

Tunables sit below; defaults are conservative for fresh-pair numbers in
their first 21 days, then loosen.

Cost: zero LLM, two Mongo reads + one upsert per inbound. ~3ms.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from pymongo import ASCENDING

from database import get_db

log = structlog.get_logger()


WINDOW_SECONDS         = 300     # 5 minutes
SPIKE_PAUSE_MINUTES    = 30      # how long auto-draft sleeps after a spike
WARMUP_INBOUND_CAP     = 25      # cap inbound-handling rate during 21-day warmup
NORMAL_INBOUND_CAP     = 60      # cap after warmup
ALERT_REPAUSE_MINUTES  = 60      # don't WhatsApp the operator more than once an hour about the same client


def _col():
    return get_db()["spike_events"]


def ensure_spike_indexes() -> None:
    _col().create_index([("client_name", ASCENDING), ("at", ASCENDING)])
    # TTL so the spike-event log self-cleans after 7 days
    _col().create_index("at", expireAfterSeconds=7 * 86400)


def _client_doc(client_name: str) -> Optional[dict]:
    return get_db()["clients"].find_one(
        {"name": client_name},
        {"outreach_started_at": 1, "outreach_warmup_skip": 1,
         "spike_paused_until": 1, "spike_last_alert_at": 1,
         "owner_phone": 1, "agent_name": 1},
    )


def _in_warmup(client: dict) -> bool:
    if client.get("outreach_warmup_skip"):
        return False
    started = client.get("outreach_started_at")
    if not started:
        return True
    return (datetime.now(timezone.utc) - started) < timedelta(days=21)


def is_spike_paused(client_name: str) -> bool:
    """True if auto-drafting is currently suspended for this client."""
    if not client_name:
        return False
    c = _client_doc(client_name)
    if not c:
        return False
    until = c.get("spike_paused_until")
    return bool(until and until > datetime.now(timezone.utc))


def record_inbound_and_check(client_name: str) -> dict:
    """Record one inbound; if rate exceeds the cap, set the pause flag.

    Returns {paused: bool, just_tripped: bool, count: int, cap: int}.
    Callers (the webhook) use `just_tripped` to fire the operator alert.
    """
    if not client_name:
        return {"paused": False, "just_tripped": False, "count": 0, "cap": 0}

    now = datetime.now(timezone.utc)
    col = _col()
    col.insert_one({"client_name": client_name, "at": now})

    since = now - timedelta(seconds=WINDOW_SECONDS)
    count = col.count_documents({"client_name": client_name, "at": {"$gte": since}})

    client = _client_doc(client_name) or {}
    cap = WARMUP_INBOUND_CAP if _in_warmup(client) else NORMAL_INBOUND_CAP
    already_paused = bool(client.get("spike_paused_until") and
                          client["spike_paused_until"] > now)

    if count <= cap:
        return {"paused": already_paused, "just_tripped": False, "count": count, "cap": cap}

    # Threshold breached
    pause_until = now + timedelta(minutes=SPIKE_PAUSE_MINUTES)
    last_alert  = client.get("spike_last_alert_at")
    should_alert = (not last_alert) or (now - last_alert) > timedelta(minutes=ALERT_REPAUSE_MINUTES)

    update = {"$set": {"spike_paused_until": pause_until}}
    if should_alert:
        update["$set"]["spike_last_alert_at"] = now

    get_db()["clients"].update_one({"name": client_name}, update)
    log.warning("spike_guard_tripped",
                client=client_name, count=count, cap=cap,
                pause_until=pause_until.isoformat())

    return {"paused": True, "just_tripped": should_alert,
            "count": count, "cap": cap,
            "pause_until": pause_until.isoformat()}
