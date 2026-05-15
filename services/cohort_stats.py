"""
Cohort Stats — anonymised platform-wide aggregates.

What this produces
------------------
A single JSON document with rolling-window totals across every active client.
Used by:
  • The landing page hero (live social-proof tiles)
  • Investor decks
  • The "ReachNG community" weekly tweet ("This week we…")

No client_id appears. No business name leaves this aggregate. Just totals.

Refreshed nightly by scheduler. Read from cache on the landing page so we
don't recompute on every visitor.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from pymongo import DESCENDING

from database import get_db

log = structlog.get_logger()


def _db():
    return get_db()


def get_cohort_col():
    return _db()["cohort_stats"]


def ensure_cohort_indexes() -> None:
    get_cohort_col().create_index([("snapshot_at", DESCENDING)])


# ─── Compute ──────────────────────────────────────────────────────────────────

def compute_cohort_stats(window_days: int = 7) -> dict:
    """Roll up KPIs across every active client for the last `window_days`."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    db = _db()

    # Pull latest scorecard snapshot per client (capped to "active" clients).
    active_client_ids = [
        str(c["_id"]) for c in db["clients"].find({"active": True}, {"_id": 1})
    ]
    business_count = len(active_client_ids)

    total_ngn_closed = 0.0
    total_bookings   = 0
    total_drafts_approved = 0
    total_hours_saved = 0.0
    response_samples: list[float] = []
    approval_rates: list[float] = []

    snap_col = db["scorecard_snapshots"]
    for cid in active_client_ids:
        latest = snap_col.find_one({"client_id": cid}, sort=[("snapshot_at", -1)])
        if not latest:
            continue
        total_ngn_closed += float(latest.get("ngn_closed") or 0)
        total_bookings   += int(latest.get("bookings_closed") or 0)
        total_drafts_approved += int(latest.get("drafts_approved") or 0)
        total_hours_saved += float(latest.get("hours_saved") or 0)
        mrs = latest.get("median_response_seconds")
        if mrs is not None:
            response_samples.append(float(mrs))
        ar = latest.get("approval_rate")
        if ar is not None:
            approval_rates.append(float(ar))

    median_response = statistics.median(response_samples) if response_samples else None
    median_approval = statistics.median(approval_rates) if approval_rates else None

    # Rolling-window message volume (lightweight DB scan)
    inbound_count = db["inbound_messages"].count_documents({"received_at": {"$gte": start}})
    drafts_count_window = db["pending_approvals"].count_documents({"created_at": {"$gte": start}})

    return {
        "business_count":           business_count,
        "ngn_closed_total":         round(total_ngn_closed, 2),
        "bookings_total":           total_bookings,
        "drafts_approved_total":    total_drafts_approved,
        "hours_saved_total":        round(total_hours_saved, 1),
        "median_response_seconds":  round(median_response, 1) if median_response is not None else None,
        "median_approval_rate":     round(median_approval, 4) if median_approval is not None else None,
        "inbound_volume_window":    inbound_count,
        "drafts_in_window":         drafts_count_window,
        "window_days":              window_days,
        "computed_at":              now,
    }


def snapshot_cohort_stats(window_days: int = 7) -> dict:
    stats = compute_cohort_stats(window_days=window_days)
    stats_to_store = dict(stats)
    stats_to_store["snapshot_at"] = stats["computed_at"]
    get_cohort_col().insert_one(stats_to_store)
    return stats


def latest_cohort_stats() -> Optional[dict]:
    doc = get_cohort_col().find_one(sort=[("snapshot_at", -1)])
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


# ─── Display helpers (for landing-page tiles + tweets) ────────────────────────

def format_summary_for_landing() -> dict:
    """Returns the human-readable strings the landing page renders.

    Falls back to safe defaults when no snapshot exists yet.
    """
    s = latest_cohort_stats()
    if not s:
        return {
            "businesses":        "—",
            "ngn_this_week":     "—",
            "hours_saved":       "—",
            "response_seconds":  "—",
            "ready":             False,
        }
    def _ngn(v):
        if not v:
            return "₦0"
        if v >= 1_000_000_000:
            return f"₦{v/1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"₦{v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"₦{v/1_000:.0f}K"
        return f"₦{v:,.0f}"
    def _seconds(v):
        if v is None:
            return "—"
        if v < 60:
            return f"{int(v)}s"
        if v < 3600:
            return f"{v/60:.1f}min"
        return f"{v/3600:.1f}hr"
    return {
        "businesses":        f"{s.get('business_count', 0):,}",
        "ngn_this_week":     _ngn(s.get('ngn_closed_total') or 0),
        "hours_saved":       f"{s.get('hours_saved_total', 0):,.0f}",
        "response_seconds":  _seconds(s.get('median_response_seconds')),
        "ready":             True,
    }
