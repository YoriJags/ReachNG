"""
Usage Meter — per-client cost accounting + anti-runaway rate limit.

Why this exists
---------------
Every cost-incurring call (Whisper, Receipt Vision, Inbound Classifier,
Drafter, Memory Extractor, Co-pilot) is metered here so:
  1. Operator sees per-client API cost in the admin Billing dashboard
  2. No one client can rack up bills via abuse or runaway logic
  3. Margin math is grounded in real usage data, not guesses

How to use
----------
Wrap a function:

    from services.usage_meter import record, check_rate

    def call_whisper(client_id, audio_bytes):
        if not check_rate(client_id, "voice", max_per_minute=20):
            raise UsageRateLimitExceeded("voice")
        # ... do the call ...
        record(client_id, "voice", units=1, ngn_cost=8.0)

Or use the decorator:

    @meter("voice", cost_ngn=8.0, max_per_minute=20)
    async def transcribe_voice_note(client_id, audio_bytes):
        ...

The decorator looks for `client_id` in kwargs or positional args. If it
can't find one, it logs and skips metering (never blocks the call).

Storage
-------
  usage_events: append-only ledger { client_id, feature, units, ngn_cost, ts }
                — used for any time-window analytics + month-end billing.
  usage_quotas: rolling per-client per-feature minute / hour / month counters
                — used for fast rate-limit checks (single indexed find_one).

Features tracked (v1)
---------------------
  voice         — Whisper transcription per voice note
  receipt       — Claude vision per receipt screenshot
  classifier    — emotion read per inbound
  drafter       — Haiku draft generation
  memory        — Haiku memory extraction
  copilot       — owner co-pilot ask (planner + narrator)
"""
from __future__ import annotations

import functools
import inspect
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

import structlog
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Errors ───────────────────────────────────────────────────────────────────

class UsageRateLimitExceeded(Exception):
    """Raised when a client trips the hard per-minute rate limit on a feature."""
    def __init__(self, feature: str, scope: str = "minute"):
        super().__init__(f"rate limit exceeded for feature={feature} scope={scope}")
        self.feature = feature
        self.scope = scope


# ─── Cost defaults per feature (in ₦, rough but honest) ─────────────────────
# Tune from real data after T0.2.5 has been live for 30 days.

FEATURE_COSTS = {
    "voice":      8.0,    # Whisper, ~30-90s of audio
    "receipt":   10.0,    # Claude Haiku 4.5 vision
    "classifier": 2.0,    # Haiku, ~200-400 tokens in/out
    "drafter":    4.0,    # Haiku, ~400-700 tokens in/out
    "memory":     3.0,    # Haiku, structured extraction
    "copilot":    8.0,    # Haiku planner + narrator
}


# ─── Hard ceilings (anti-runaway) — per client, per feature, per minute ───────
# Trip = log + raise UsageRateLimitExceeded. Caller decides whether to
# degrade gracefully or surface to user.

HARD_LIMITS_PER_MIN = {
    "voice":      20,
    "receipt":    20,
    "classifier": 60,
    "drafter":    60,
    "memory":     60,
    "copilot":    15,
}


# ─── Collections ──────────────────────────────────────────────────────────────

def _events():
    return get_db()["usage_events"]


def _quotas():
    return get_db()["usage_quotas"]


def ensure_usage_indexes() -> None:
    e = _events()
    e.create_index([("client_id", ASCENDING), ("feature", ASCENDING), ("ts", DESCENDING)])
    e.create_index([("ts", DESCENDING)])
    e.create_index([("client_id", ASCENDING), ("ts", DESCENDING)])

    q = _quotas()
    q.create_index([("client_id", ASCENDING), ("feature", ASCENDING),
                     ("bucket", ASCENDING), ("bucket_key", ASCENDING)], unique=True)


# ─── Bucket keys ──────────────────────────────────────────────────────────────

def _minute_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M")


def _month_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m")


# ─── Rate-limit check ────────────────────────────────────────────────────────

def check_rate(client_id: str, feature: str,
                max_per_minute: Optional[int] = None) -> bool:
    """Returns True if the call is allowed, False if it would exceed the
    per-minute hard ceiling for this client+feature.
    """
    if not client_id:
        return True   # platform-level calls (no client scope) skip the gate
    limit = max_per_minute if max_per_minute is not None else HARD_LIMITS_PER_MIN.get(feature, 100)
    now = datetime.now(timezone.utc)
    doc = _quotas().find_one({
        "client_id": str(client_id),
        "feature":   feature,
        "bucket":    "minute",
        "bucket_key": _minute_key(now),
    }, {"count": 1})
    count = (doc or {}).get("count", 0)
    if count >= limit:
        log.warning("usage_rate_limit_hit",
                    client_id=client_id, feature=feature, count=count, limit=limit)
        return False
    return True


# ─── Record ──────────────────────────────────────────────────────────────────

def record(client_id: Optional[str], feature: str,
            units: int = 1, ngn_cost: Optional[float] = None,
            extra: Optional[dict] = None) -> None:
    """Append one usage event + bump the per-bucket counters."""
    now = datetime.now(timezone.utc)
    cost = float(ngn_cost) if ngn_cost is not None else float(FEATURE_COSTS.get(feature, 0))
    doc = {
        "client_id": str(client_id) if client_id else None,
        "feature":   feature,
        "units":     units,
        "ngn_cost":  cost,
        "ts":        now,
    }
    if extra:
        doc["extra"] = extra
    try:
        _events().insert_one(doc)
    except Exception as e:
        log.warning("usage_record_failed", error=str(e))
        return

    if not client_id:
        return
    # Bucket counters — single upsert per bucket scope
    for bucket, key in (("minute", _minute_key(now)),
                         ("month",  _month_key(now))):
        try:
            _quotas().update_one(
                {"client_id": str(client_id), "feature": feature,
                 "bucket": bucket, "bucket_key": key},
                {"$inc": {"count": units, "ngn_cost": cost},
                 "$set": {"updated_at": now}},
                upsert=True,
            )
        except Exception as e:
            log.warning("usage_quota_upsert_failed", error=str(e),
                        client_id=client_id, feature=feature, bucket=bucket)


# ─── Decorator ───────────────────────────────────────────────────────────────

def meter(feature: str, cost_ngn: Optional[float] = None,
           max_per_minute: Optional[int] = None,
           client_id_arg: str = "client_id"):
    """Decorator: rate-check, run, then record. Works for sync + async.

    Looks for `client_id` in kwargs, then in positional args by inspecting the
    wrapped function's signature. If absent, the call still runs (no scope to
    meter against) but is recorded with client_id=None.

    On rate-limit hit: raises UsageRateLimitExceeded — caller can catch and
    degrade gracefully.
    """
    def deco(fn: Callable):
        sig = inspect.signature(fn)
        param_names = list(sig.parameters.keys())

        def _extract_client_id(args, kwargs):
            if client_id_arg in kwargs:
                return kwargs.get(client_id_arg)
            if client_id_arg in param_names:
                idx = param_names.index(client_id_arg)
                if idx < len(args):
                    return args[idx]
            return None

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrap(*args, **kwargs):
                cid = _extract_client_id(args, kwargs)
                if cid and not check_rate(str(cid), feature, max_per_minute):
                    raise UsageRateLimitExceeded(feature)
                result = await fn(*args, **kwargs)
                record(cid, feature, units=1, ngn_cost=cost_ngn)
                return result
            return awrap
        @functools.wraps(fn)
        def swrap(*args, **kwargs):
            cid = _extract_client_id(args, kwargs)
            if cid and not check_rate(str(cid), feature, max_per_minute):
                raise UsageRateLimitExceeded(feature)
            result = fn(*args, **kwargs)
            record(cid, feature, units=1, ngn_cost=cost_ngn)
            return result
        return swrap
    return deco


# ─── Reads (for admin billing dashboard) ──────────────────────────────────────

def usage_for_client(client_id: str, *, days: int = 30) -> dict:
    """Aggregate usage + cost for one client over the last `days`."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"client_id": str(client_id), "ts": {"$gte": since}}},
        {"$group": {"_id": "$feature", "count": {"$sum": "$units"},
                     "ngn_cost": {"$sum": "$ngn_cost"}}},
        {"$sort": {"ngn_cost": -1}},
    ]
    rows = list(_events().aggregate(pipeline))
    total_cost = sum(r.get("ngn_cost", 0) for r in rows)
    total_calls = sum(r.get("count", 0) for r in rows)
    return {
        "client_id":  str(client_id),
        "since_days": days,
        "by_feature": [{"feature": r["_id"], "calls": r["count"],
                         "ngn_cost": round(r["ngn_cost"], 2)} for r in rows],
        "total_cost": round(total_cost, 2),
        "total_calls": total_calls,
    }


def billing_table(*, days: int = 30) -> list[dict]:
    """One row per active client with revenue, cost, margin. Surfaced in the
    admin Billing dashboard."""
    db = get_db()
    rows = []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    for c in db["clients"].find({"active": True},
                                  {"_id": 1, "name": 1, "plan": 1,
                                   "monthly_fee_ngn": 1, "payment_status": 1}):
        cid = str(c["_id"])
        usage = usage_for_client(cid, days=days)
        revenue = float(c.get("monthly_fee_ngn") or 0)
        cost = usage["total_cost"]
        margin_ngn = revenue - cost
        margin_pct = round((margin_ngn / revenue) * 100, 1) if revenue > 0 else None
        # Top feature by spend
        top_feature = usage["by_feature"][0]["feature"] if usage["by_feature"] else None
        # "At risk" flag if margin < 70%
        at_risk = margin_pct is not None and margin_pct < 70
        rows.append({
            "client_id":     cid,
            "name":          c.get("name"),
            "plan":          c.get("plan"),
            "payment_status": c.get("payment_status"),
            "revenue_ngn":   revenue,
            "cost_ngn":      round(cost, 2),
            "margin_ngn":    round(margin_ngn, 2),
            "margin_pct":    margin_pct,
            "calls":         usage["total_calls"],
            "top_feature":   top_feature,
            "at_risk":       at_risk,
        })
    rows.sort(key=lambda r: (r["at_risk"], -((r["margin_pct"] or 100) * -1)),
               reverse=True)
    return rows
