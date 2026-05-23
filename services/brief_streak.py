"""
Owner-brief streak counter (SPRINT 2 #7).

Why
---
Premium owners open WhatsApp first thing every morning. The Owner Brief is
the daily anchor. Adding a streak count + cumulative-deposits headline turns
the brief from "useful summary" into "habit hook + visible ROI."

Storage
-------
  brief_sends collection — one row per successful brief delivery:
    { client_name, sent_at, day_str (YYYY-MM-DD in Lagos) }

Public
------
  record_send(client_name)            → call after a brief sends successfully
  compute_streak(client_name)         → returns {days, started_at}
  cumulative_deposits_ngn(client_name) → sum of confirmed Paystack events since
                                          client.client_onboarded_at (or signup)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import re

import structlog

from database import get_db

log = structlog.get_logger()

_LAGOS_OFFSET = timedelta(hours=1)   # WAT, no DST


def _brief_sends():
    return get_db()["brief_sends"]


def _day_str_lagos(dt: Optional[datetime] = None) -> str:
    """YYYY-MM-DD in Africa/Lagos (UTC+1, no DST)."""
    t = (dt or datetime.now(timezone.utc)) + _LAGOS_OFFSET
    return t.strftime("%Y-%m-%d")


# ─── Recording ───────────────────────────────────────────────────────────────

def record_send(client_name: str) -> None:
    """Idempotent per Lagos day — calling twice on the same day doesn't
    inflate the streak."""
    now = datetime.now(timezone.utc)
    day = _day_str_lagos(now)
    try:
        _brief_sends().update_one(
            {"client_name": client_name, "day_str": day},
            {"$setOnInsert": {"client_name": client_name, "day_str": day, "sent_at": now}},
            upsert=True,
        )
    except Exception as e:
        log.warning("brief_send_record_failed", client=client_name, error=str(e))


# ─── Streak math ─────────────────────────────────────────────────────────────

def compute_streak(client_name: str) -> dict:
    """Count consecutive Lagos calendar days the brief was sent, ending today.
    Returns {days, started_at} — days=0 if no brief today yet.
    """
    today = _day_str_lagos()
    yesterday = _day_str_lagos(datetime.now(timezone.utc) - timedelta(days=1))

    # Pull most recent ~60 days of sends sorted desc — plenty for any plausible streak
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    sends = list(_brief_sends().find(
        {"client_name": client_name, "sent_at": {"$gte": cutoff}},
        projection={"day_str": 1, "sent_at": 1, "_id": 0},
    ).sort("day_str", -1))

    if not sends:
        return {"days": 0, "started_at": None}

    days_set = {row["day_str"] for row in sends}
    # Streak counts from today (if sent) or yesterday (if today not yet sent).
    cursor_day = today if today in days_set else (yesterday if yesterday in days_set else None)
    if not cursor_day:
        return {"days": 0, "started_at": None}

    streak = 0
    earliest = cursor_day
    while cursor_day in days_set:
        streak += 1
        earliest = cursor_day
        prev = datetime.strptime(cursor_day, "%Y-%m-%d") - timedelta(days=1)
        cursor_day = prev.strftime("%Y-%m-%d")

    return {"days": streak, "started_at": earliest}


# ─── Cumulative deposits caught ──────────────────────────────────────────────

def cumulative_deposits_ngn(client_name: str) -> int:
    """Sum of confirmed Paystack receipts attributed to this client since
    their `client_onboarded_at` (or signup). Returns naira amount."""
    clients = get_db()["clients"]
    client = clients.find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
        projection={"client_onboarded_at": 1, "onboarded_at": 1, "created_at": 1},
    )
    if not client:
        return 0
    since = (client.get("client_onboarded_at")
             or client.get("onboarded_at")
             or client.get("created_at")
             or (datetime.now(timezone.utc) - timedelta(days=30)))

    # Sum receipt screenshots parsed for this client + confirmed Paystack events
    total = 0
    try:
        # confirmed receipts via Receipt Catcher
        rec_pipeline = [
            {"$match": {
                "client_name": client_name,
                "status":      "confirmed",
                "confirmed_at": {"$gte": since},
            }},
            {"$group": {"_id": None, "ngn": {"$sum": "$amount_ngn"}}},
        ]
        for row in get_db()["receipt_matches"].aggregate(rec_pipeline):
            total += int(row.get("ngn") or 0)
    except Exception:
        pass
    try:
        # Paystack subscription deposits for any bookings/invoices recorded for this client
        ps_pipeline = [
            {"$match": {
                "client_name": client_name,
                "event":       "charge.success",
                "paid_at":     {"$gte": since},
            }},
            {"$group": {"_id": None, "ngn": {"$sum": "$amount_ngn"}}},
        ]
        for row in get_db()["paystack_events"].aggregate(ps_pipeline):
            total += int(row.get("ngn") or 0)
    except Exception:
        pass

    return int(total)


# ─── Index ──────────────────────────────────────────────────────────────────

def ensure_brief_streak_indexes() -> None:
    coll = _brief_sends()
    coll.create_index(
        [("client_name", 1), ("day_str", -1)],
        name="brief_sends_client_day", unique=True,
    )
    coll.create_index([("sent_at", -1)], name="brief_sends_recent")
