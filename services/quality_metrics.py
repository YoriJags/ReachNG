"""
Quality Metrics — the moat indicator nobody else builds.

Tracks how well our drafts match each client's voice over time. A drop in
approval rate is the canary for prompt drift, stale brief, or shifting client
priorities — we want to see it before the client churns.

What's tracked
--------------
For one client over a window:
  • approval_rate          — approved / actioned (excl. pending). Voice match.
  • edit_distance_pct      — avg %-of-message edited before send. Draft fidelity.
  • skip_rate              — skipped / actioned. Relevance.
  • avg_time_to_approve_s  — median seconds from queue → approve. Owner trust.
  • customer_reply_rate    — % of approved drafts that got a customer reply
                              within 48h. Conversion power.

Drift alarm
-----------
If approval_rate drops by more than DRIFT_THRESHOLD vs the prior window, log
ERROR + persist to `quality_alerts` for operator surfacing.

Scope: every call REQUIRES client_id (resolved by name internally where needed).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()

DRIFT_THRESHOLD = 0.15      # 15-pt drop in approval rate triggers an alert
REPLY_WINDOW_HOURS = 48


# ─── Errors ───────────────────────────────────────────────────────────────────

class QualityScopeError(Exception):
    """Refuses calls without client_id."""


# ─── Accessors ───────────────────────────────────────────────────────────────

def _db():
    return get_db()


def get_alerts_col():
    return _db()["quality_alerts"]


def ensure_quality_indexes() -> None:
    al = get_alerts_col()
    al.create_index([("client_id", ASCENDING), ("ts", DESCENDING)])
    al.create_index([("ts", DESCENDING)])


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class QualityReport:
    client_id:                 str
    client_name:               Optional[str]
    window_days:               int
    drafts_actioned:           int = 0
    drafts_approved:           int = 0
    drafts_edited:             int = 0
    drafts_skipped:            int = 0
    approval_rate:             float = 0.0
    edit_distance_pct:         Optional[float] = None
    skip_rate:                 float = 0.0
    avg_time_to_approve_s:     Optional[float] = None
    customer_reply_rate:       Optional[float] = None
    approval_rate_prev_window: Optional[float] = None
    drift_detected:            bool = False


# ─── Scope ───────────────────────────────────────────────────────────────────

def _require(client_id: Optional[str]) -> str:
    if not client_id or not str(client_id).strip():
        raise QualityScopeError("quality_metrics requires client_id")
    return str(client_id).strip()


def _client_name(client_id: str) -> Optional[str]:
    try:
        doc = _db()["clients"].find_one({"_id": ObjectId(client_id)}, {"name": 1})
    except Exception:
        return None
    return (doc or {}).get("name")


# ─── Core compute ────────────────────────────────────────────────────────────

def _approval_rate(client_name: str, start: datetime, end: datetime) -> tuple[float, dict, list]:
    """Returns (approval_rate, counts, sample_of_approved_records).
    Sample is used downstream for edit-distance and reply-rate calc."""
    col = _db()["pending_approvals"]
    cursor = col.find({
        "client_name": client_name,
        "created_at":  {"$gte": start, "$lt": end},
        "status":      {"$in": ["approved", "auto_sent", "edited", "skipped"]},
    }, {"status": 1, "message": 1, "edited_message": 1, "actioned_at": 1,
        "created_at": 1, "phone": 1})
    counts = {"approved": 0, "auto_sent": 0, "edited": 0, "skipped": 0}
    sample: list[dict] = []
    for d in cursor:
        s = (d.get("status") or "").lower()
        if s in counts:
            counts[s] += 1
        if s in {"approved", "auto_sent"}:
            sample.append(d)
    approved = counts["approved"] + counts["auto_sent"]
    actioned = approved + counts["edited"] + counts["skipped"]
    rate = (approved / actioned) if actioned else 0.0
    return rate, counts, sample


def _edit_distance_pct(name: str, start: datetime, end: datetime) -> Optional[float]:
    """Avg percentage of message edited (Levenshtein-like via length diff)."""
    col = _db()["pending_approvals"]
    cursor = col.find({
        "client_name":     name,
        "status":          "edited",
        "actioned_at":     {"$gte": start, "$lt": end},
        "edited_message":  {"$exists": True, "$ne": None},
    }, {"message": 1, "edited_message": 1})
    pcts: list[float] = []
    for d in cursor:
        orig = (d.get("message") or "")
        edit = (d.get("edited_message") or "")
        if not orig:
            continue
        # Cheap proxy: char-diff over original length
        diff = abs(len(edit) - len(orig)) + sum(
            1 for a, b in zip(orig, edit) if a != b
        )
        pcts.append(min(1.0, diff / max(1, len(orig))))
    if not pcts:
        return None
    return round(statistics.mean(pcts), 4)


def _customer_reply_rate(approved_drafts: list[dict]) -> Optional[float]:
    """Of the approved/auto_sent drafts, what fraction got an inbound reply
    from the same phone within REPLY_WINDOW_HOURS?"""
    if not approved_drafts:
        return None
    inbound = _db()["inbound_messages"]
    hits = 0
    eligible = 0
    for d in approved_drafts[:300]:  # cap for performance
        phone = d.get("phone")
        actioned = d.get("actioned_at")
        if not (phone and actioned):
            continue
        eligible += 1
        cutoff = actioned + timedelta(hours=REPLY_WINDOW_HOURS)
        if inbound.find_one({
            "sender_phone": phone,
            "received_at":  {"$gt": actioned, "$lt": cutoff},
        }, {"_id": 1}):
            hits += 1
    if not eligible:
        return None
    return round(hits / eligible, 4)


def _avg_time_to_approve(name: str, start: datetime, end: datetime) -> Optional[float]:
    col = _db()["pending_approvals"]
    pairs = []
    cursor = col.find({
        "client_name": name,
        "status":      {"$in": ["approved", "auto_sent"]},
        "actioned_at": {"$gte": start, "$lt": end},
    }, {"created_at": 1, "actioned_at": 1}).limit(300)
    for d in cursor:
        if d.get("created_at") and d.get("actioned_at"):
            delta = (d["actioned_at"] - d["created_at"]).total_seconds()
            if 0 < delta < 7 * 24 * 3600:
                pairs.append(delta)
    if not pairs:
        return None
    return float(statistics.median(pairs))


# ─── Public ──────────────────────────────────────────────────────────────────

def compute_quality(client_id: str, window_days: int = 14) -> QualityReport:
    cid = _require(client_id)
    cname = _client_name(cid)
    if not cname:
        return QualityReport(client_id=cid, client_name=None, window_days=window_days)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    prev_start = start - timedelta(days=window_days)

    rate, counts, sample = _approval_rate(cname, start, now)
    prev_rate, _, _ = _approval_rate(cname, prev_start, start)
    edit_pct = _edit_distance_pct(cname, start, now)
    reply_rate = _customer_reply_rate(sample)
    time_to_approve = _avg_time_to_approve(cname, start, now)

    approved = counts.get("approved", 0) + counts.get("auto_sent", 0)
    edited = counts.get("edited", 0)
    skipped = counts.get("skipped", 0)
    actioned = approved + edited + skipped
    skip_rate = (skipped / actioned) if actioned else 0.0

    drift = False
    if prev_rate >= 0.5 and rate < prev_rate - DRIFT_THRESHOLD:
        drift = True

    report = QualityReport(
        client_id=cid,
        client_name=cname,
        window_days=window_days,
        drafts_actioned=actioned,
        drafts_approved=approved,
        drafts_edited=edited,
        drafts_skipped=skipped,
        approval_rate=round(rate, 4),
        edit_distance_pct=edit_pct,
        skip_rate=round(skip_rate, 4),
        avg_time_to_approve_s=time_to_approve,
        customer_reply_rate=reply_rate,
        approval_rate_prev_window=round(prev_rate, 4),
        drift_detected=drift,
    )

    if drift:
        try:
            get_alerts_col().insert_one({
                "client_id":      cid,
                "client_name":    cname,
                "ts":             now,
                "kind":           "approval_drift",
                "current_rate":   rate,
                "previous_rate":  prev_rate,
                "window_days":    window_days,
            })
            log.error("quality_drift_alert", client=cname,
                      current=rate, previous=prev_rate)
        except Exception as e:
            log.warning("quality_alert_persist_failed", error=str(e))

    return report


def compute_quality_all_clients(window_days: int = 14) -> list[QualityReport]:
    out: list[QualityReport] = []
    for c in _db()["clients"].find({"active": True}, {"_id": 1}):
        try:
            out.append(compute_quality(str(c["_id"]), window_days))
        except Exception as e:
            log.warning("quality_compute_failed", client_id=str(c["_id"]), error=str(e))
    return out
