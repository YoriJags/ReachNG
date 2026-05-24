"""
Closer-lead revival job (BACKLOG P0 #7).

Drafter already exists (`draft_next_move`). What was missing: nothing
re-triggered it after the customer went quiet. This module scans for leads
that have stalled at a non-terminal stage past a per-stage threshold and
re-queues a contextual revival draft through HITL.

Per-stage quiet thresholds (in days, since `updated_at`):
    new          → 2
    qualifying   → 3
    ready        → 4
    stalled/lost/booked → never

Guard rails (avoid spam loops):
    • Skip if any out-direction thread entry exists in the last
      MIN_GAP_DAYS (default 2) — prevents drafting on top of a pending HITL
      draft that the owner hasn't approved yet.
    • Stamp `last_revival_at` on the lead so we don't redraft the same
      lead more than once per `MIN_REVIVAL_INTERVAL_DAYS` (default 5).
    • Respect the owner-pause gate by going through `draft_next_move`
      itself (which already checks `eyo_paused_until`).

Wired into APScheduler — runs every 4h at :17 past, Africa/Lagos.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from bson import ObjectId

from database import get_db

log = structlog.get_logger()

# Per-stage quiet threshold in days
STAGE_QUIET_DAYS: dict[str, int] = {
    "new":        2,
    "qualifying": 3,
    "ready":      4,
}

MIN_GAP_DAYS = 2                # Don't redraft if we drafted in this window
MIN_REVIVAL_INTERVAL_DAYS = 5   # Per-lead floor between revivals
MAX_PER_RUN = 50


def _col():
    return get_db()["closer_leads"]


def _recent_outbound(lead: dict, since: datetime) -> bool:
    for ev in reversed(lead.get("thread") or []):
        at = ev.get("at")
        if at and at < since:
            return False
        if ev.get("direction") == "out" and at and at >= since:
            return True
    return False


async def run_revival_sweep() -> dict:
    """Find quiet leads, queue revival drafts via the existing drafter."""
    now = datetime.now(timezone.utc)
    summary = {"scanned": 0, "drafted": 0, "skipped_recent_outbound": 0,
               "skipped_recent_revival": 0, "errors": 0}

    # Cheap pre-filter — Mongo finds leads whose updated_at is older than the
    # tightest threshold (2 days). Per-stage threshold applied in Python.
    cutoff = now - timedelta(days=min(STAGE_QUIET_DAYS.values()))
    q = {
        "stage":      {"$in": list(STAGE_QUIET_DAYS.keys())},
        "updated_at": {"$lt": cutoff},
    }
    cursor = _col().find(q).sort("updated_at", 1).limit(MAX_PER_RUN)

    for lead in cursor:
        summary["scanned"] += 1
        try:
            stage = lead.get("stage")
            threshold_days = STAGE_QUIET_DAYS.get(stage)
            if not threshold_days:
                continue
            updated_at = lead.get("updated_at")
            if not updated_at or (now - updated_at) < timedelta(days=threshold_days):
                continue

            # Per-lead revival floor
            last_rev = lead.get("last_revival_at")
            if last_rev and (now - last_rev) < timedelta(days=MIN_REVIVAL_INTERVAL_DAYS):
                summary["skipped_recent_revival"] += 1
                continue

            # Don't pile on top of a pending HITL draft
            since = now - timedelta(days=MIN_GAP_DAYS)
            if _recent_outbound(lead, since):
                summary["skipped_recent_outbound"] += 1
                continue

            lead_id = str(lead["_id"])
            try:
                from services.closer.brain import draft_next_move
                result = draft_next_move(lead_id)
            except Exception as e:
                log.warning("revival_draft_failed", lead=lead_id, error=str(e))
                summary["errors"] += 1
                continue

            if result:
                _col().update_one(
                    {"_id": ObjectId(lead_id)},
                    {"$set": {"last_revival_at": now}},
                )
                summary["drafted"] += 1
        except Exception as e:
            log.error("revival_sweep_lead_failed", error=str(e))
            summary["errors"] += 1

    log.info("closer_revival_sweep_done", **summary)
    return summary
