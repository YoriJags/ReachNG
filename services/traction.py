"""
Traction roll-up — the North-Star scoreboard (see docs/NORTH_STAR.md, C4).

Aggregates, across the whole client book, the numbers an acquirer / investor
actually asks for, from data EYO already collects. Pure read-side: no writes,
no HITL change, no tenant-isolation surface. Doubles as the fundraising deck.

Headline numbers:
  • ₦ recovered (estimated, conservative) — money EYO helped close
  • active clients + 30-day cohort retention
  • messages handled + channel mix (WhatsApp / email / Meta)
  • HITL throughput (drafts approved) + win rate

Estimation is deliberately conservative and clearly labelled: we value each
'win' outcome at a floor deal size rather than overstate. Honest numbers travel
further than flattering ones.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from database import get_db

log = structlog.get_logger()

# Conservative floor value per closed win, in NGN. Mirrors deal_value.DEFAULT_DEAL_NGN.
# Used only for the *estimated* recovered figure, which is labelled as such.
_FLOOR_WIN_NGN = 50_000

_SENT_STATUSES = ("approved", "edited", "auto_sent")


def traction_summary(*, days: int = 30) -> dict:
    """Whole-book roll-up. `days` scopes the message/outcome activity window;
    client counts are all-time / cohort-based. Never raises — degrades to zeros
    so the panel always renders."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cohort_cutoff = now - timedelta(days=30)
    db = get_db()

    clients = _client_stats(db, cohort_cutoff)
    outcomes = _outcome_stats(db, cutoff)
    messages = _message_stats(db, cutoff)

    est_recovered = outcomes["wins"] * _FLOOR_WIN_NGN

    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "headline": {
            "est_value_recovered_ngn": est_recovered,
            "est_value_basis": f"{outcomes['wins']} wins × ₦{_FLOOR_WIN_NGN:,} floor (conservative estimate)",
            "active_clients": clients["active"],
            "messages_handled": messages["total"],
        },
        "clients": clients,
        "outcomes": outcomes,
        "messages": messages,
    }


def _client_stats(db, cohort_cutoff: datetime) -> dict:
    try:
        col = db["clients"]
        active = col.count_documents({"active": True})
        paid = col.count_documents({"active": True, "payment_status": "paid"})
        # 30-day cohort retention: onboarded ≥30d ago AND still active = survived.
        cohort = col.count_documents({"onboarded_at": {"$lte": cohort_cutoff}})
        retained = col.count_documents(
            {"onboarded_at": {"$lte": cohort_cutoff}, "active": True}
        )
        retention_pct = round(100 * retained / cohort, 1) if cohort else None
        return {
            "active": active,
            "paid": paid,
            "cohort_30d": cohort,
            "retained_30d": retained,
            "retention_30d_pct": retention_pct,
        }
    except Exception as e:
        log.warning("traction_client_stats_failed", error=str(e))
        return {"active": 0, "paid": 0, "cohort_30d": 0, "retained_30d": 0, "retention_30d_pct": None}


def _outcome_stats(db, cutoff: datetime) -> dict:
    try:
        col = db["outcomes"]
        wins = col.count_documents({"status": "win", "resolved_at": {"$gte": cutoff}})
        misses = col.count_documents({"status": "miss", "resolved_at": {"$gte": cutoff}})
        resolved = wins + misses
        win_rate = round(100 * wins / resolved, 1) if resolved else None
        return {"wins": wins, "misses": misses, "resolved": resolved, "win_rate_pct": win_rate}
    except Exception as e:
        log.warning("traction_outcome_stats_failed", error=str(e))
        return {"wins": 0, "misses": 0, "resolved": 0, "win_rate_pct": None}


def _message_stats(db, cutoff: datetime) -> dict:
    try:
        col = db["pending_approvals"]
        total = col.count_documents({"created_at": {"$gte": cutoff}})
        approved = col.count_documents(
            {"created_at": {"$gte": cutoff}, "status": {"$in": list(_SENT_STATUSES)}}
        )
        # Channel mix over the window.
        mix: dict[str, int] = {}
        for row in col.aggregate([
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$channel", "count": {"$sum": 1}}},
        ]):
            mix[row["_id"] or "unknown"] = row["count"]
        return {"total": total, "approved": approved, "channel_mix": mix}
    except Exception as e:
        log.warning("traction_message_stats_failed", error=str(e))
        return {"total": 0, "approved": 0, "channel_mix": {}}
