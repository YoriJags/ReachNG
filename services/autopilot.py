"""
Autopilot readiness gate (SPRINT 1 #5c).

Rule (locked in PLAN.md): "Autopilot is earned, not defaulted."

Before an owner can flip the Autopilot toggle ON, two conditions must be met
in the last 30 days:
  1. At least N approved drafts (default 20) — enough signal to trust the agent
  2. Unedited approval rate >= 70% — drafts going out clean, not heavily rewritten

This module exposes:
  - compute_readiness(client_name)  — returns the meter values + a `ready` bool
  - assert_eligible(client_name)    — raises AutopilotNotReadyError if not ready
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

from database import get_db

log = structlog.get_logger()


# ─── Threshold knobs ─────────────────────────────────────────────────────────

MIN_APPROVALS = 20         # bumped from 10 per founder call 2026-05-21
MIN_UNEDITED_RATE = 0.70   # 70% of approvals must go out clean (not edited)
LOOKBACK_DAYS = 30


class AutopilotNotReadyError(Exception):
    """Raised when a client tries to enable Autopilot before meeting the gate."""
    def __init__(self, readiness: dict):
        self.readiness = readiness
        super().__init__(
            f"Autopilot not yet earned — {readiness.get('approvals_count', 0)}/"
            f"{readiness.get('threshold', MIN_APPROVALS)} approvals, "
            f"{int(readiness.get('unedited_pct', 0) * 100)}% unedited tone match"
        )


@dataclass
class Readiness:
    approvals_count:   int
    edited_count:      int
    unedited_count:    int
    unedited_pct:      float    # 0.0–1.0
    threshold:         int      # min approvals required
    rate_threshold:    float    # min unedited rate required
    ready:             bool
    lookback_days:     int

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Public ──────────────────────────────────────────────────────────────────

def compute_readiness(client_name: str) -> Readiness:
    """Read the approvals collection for this client in the lookback window
    and compute the meter values."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    approvals = get_db()["approvals"]

    # Approved = sent without edits (clean tone match)
    # auto_sent = sent on existing autopilot (counts as approved-equivalent)
    # edited = sent after owner edit (still a positive signal but not clean)
    # We exclude "skipped" and "pending" from the denominator.
    pipeline = [
        {"$match": {
            "client_name": client_name,
            "status":      {"$in": ["approved", "auto_sent", "edited"]},
            "actioned_at": {"$gte": cutoff},
        }},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    counts = {row["_id"]: int(row["count"]) for row in approvals.aggregate(pipeline)}
    approved   = counts.get("approved", 0) + counts.get("auto_sent", 0)
    edited     = counts.get("edited", 0)
    total      = approved + edited
    unedited_pct = (approved / total) if total > 0 else 0.0

    ready = (total >= MIN_APPROVALS) and (unedited_pct >= MIN_UNEDITED_RATE)

    return Readiness(
        approvals_count = total,
        edited_count    = edited,
        unedited_count  = approved,
        unedited_pct    = round(unedited_pct, 3),
        threshold       = MIN_APPROVALS,
        rate_threshold  = MIN_UNEDITED_RATE,
        ready           = ready,
        lookback_days   = LOOKBACK_DAYS,
    )


_PRICE_TOKENS   = ("price", "quote", "cost", "fee", "₦", "naira", "ngn", "rate", "package")
_PAYMENT_TOKENS = ("account", "transfer", "deposit", "paid", "payment", "balance",
                   "gtb", "opay", "kuda", "uba", "moniepoint")
_MIN_DIM_SAMPLE = 3   # below this we say "still learning" rather than fake a score


def _dim_score(rows: list[dict], predicate) -> tuple[Optional[int], int]:
    """Unedited rate (0–100) over the subset of approvals matching predicate.
    Returns (score|None, sample_count). None when sample too thin to be honest."""
    sub = [r for r in rows if predicate(r)]
    if len(sub) < _MIN_DIM_SAMPLE:
        return None, len(sub)
    clean = sum(1 for r in sub if r.get("status") in ("approved", "auto_sent"))
    return round(clean / len(sub) * 100), len(sub)


def readiness_breakdown(client_name: str) -> dict:
    """The 4-dimension Autopilot readiness card: tone / price / escalation /
    payment. Each is the unedited-approval rate on the slice of drafts that
    actually exercised that skill — honest 'still learning' when sparse."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    rows = list(get_db()["approvals"].find(
        {"client_name": client_name,
         "status": {"$in": ["approved", "auto_sent", "edited"]},
         "actioned_at": {"$gte": cutoff}},
        {"status": 1, "message": 1, "classification": 1},
    ))

    def _has(tokens):
        return lambda r: any(t in (r.get("message") or "").lower() for t in tokens)

    def _is_escalation(r):
        urg = (r.get("classification") or {}).get("urgency")
        return str(urg).lower() in ("high", "urgent", "hot")

    tone_score, tone_n = _dim_score(rows, lambda r: True)
    price_score, price_n = _dim_score(rows, _has(_PRICE_TOKENS))
    esc_score, esc_n     = _dim_score(rows, _is_escalation)
    pay_score, pay_n     = _dim_score(rows, _has(_PAYMENT_TOKENS))

    dims = [
        {"key": "tone",       "label": "Tone match",         "score": tone_score,  "sample": tone_n},
        {"key": "price",      "label": "Price accuracy",     "score": price_score, "sample": price_n},
        {"key": "escalation", "label": "Escalation judgment","score": esc_score,   "sample": esc_n},
        {"key": "payment",    "label": "Payment handling",   "score": pay_score,   "sample": pay_n},
    ]
    scored = [d["score"] for d in dims if d["score"] is not None]
    overall = round(sum(scored) / len(scored)) if scored else 0
    r = compute_readiness(client_name)
    return {
        "overall_pct":  overall,
        "ready":        r.ready,
        "approvals_count": r.approvals_count,
        "threshold":    r.threshold,
        "dimensions":   dims,
        "headline":     f"EYO is {overall}% ready to handle replies on its own.",
    }


def assert_eligible(client_name: str) -> Readiness:
    """Raise AutopilotNotReadyError if the client hasn't earned Autopilot yet.
    Returns the Readiness on success."""
    r = compute_readiness(client_name)
    if not r.ready:
        raise AutopilotNotReadyError(r.to_dict())
    return r
