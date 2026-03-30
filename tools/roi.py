"""
ROI tracking — logs the naira value of every message sent.
Compares AI cost vs manual outreach cost.
Shows clients exactly what ReachNG is worth.
"""
from datetime import datetime, timezone, timedelta
from database import get_db, get_outreach_log
from config import get_settings
import structlog

log = structlog.get_logger()

# ─── Cost constants (adjustable per client) ───────────────────────────────────
MANUAL_COST_PER_MESSAGE_NGN = 2_000   # Cost of one manual outreach (staff time)
API_COST_PER_MESSAGE_NGN    = 15      # Claude + Unipile per message (~$0.01)


def get_roi_collection():
    return get_db()["roi_log"]


def ensure_roi_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_roi_collection()
    col.create_index([("logged_at", DESCENDING)])
    col.create_index([("vertical", ASCENDING)])
    col.create_index([("client_name", ASCENDING)])


def log_roi_event(
    contact_name: str,
    vertical: str,
    channel: str,
    client_name: str | None = None,
    manual_cost: int = MANUAL_COST_PER_MESSAGE_NGN,
    api_cost: int = API_COST_PER_MESSAGE_NGN,
):
    """Log the ROI value of one sent message."""
    get_roi_collection().insert_one({
        "contact_name": contact_name,
        "vertical": vertical,
        "channel": channel,
        "client_name": client_name,
        "manual_cost_ngn": manual_cost,
        "api_cost_ngn": api_cost,
        "value_generated_ngn": manual_cost - api_cost,
        "logged_at": datetime.now(timezone.utc),
    })


def get_roi_summary(days: int = 30, client_name: str | None = None) -> dict:
    """
    Calculate total ROI for the last N days.
    Returns naira values and percentage ROI.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = {"logged_at": {"$gte": since}}
    if client_name:
        query["client_name"] = client_name

    col = get_roi_collection()
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "messages_sent":        {"$sum": 1},
            "manual_cost_total":    {"$sum": "$manual_cost_ngn"},
            "api_cost_total":       {"$sum": "$api_cost_ngn"},
            "value_generated_total":{"$sum": "$value_generated_ngn"},
        }},
    ]
    rows = list(col.aggregate(pipeline))

    if not rows:
        return {
            "period_days": days,
            "messages_sent": 0,
            "manual_equivalent_ngn": 0,
            "api_cost_ngn": 0,
            "value_generated_ngn": 0,
            "roi_percent": 0,
            "roi_label": "No activity yet",
        }

    r = rows[0]
    manual  = r["manual_cost_total"]
    api     = r["api_cost_total"]
    value   = r["value_generated_total"]
    roi_pct = round((value / api) * 100) if api > 0 else 0

    return {
        "period_days": days,
        "messages_sent": r["messages_sent"],
        "manual_equivalent_ngn": manual,
        "api_cost_ngn": api,
        "value_generated_ngn": value,
        "roi_percent": roi_pct,
        "roi_label": f"₦{value:,} generated for ₦{api:,} spent — {roi_pct}x ROI",
    }


def get_roi_by_vertical(days: int = 30) -> list[dict]:
    """ROI breakdown per vertical."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    col = get_roi_collection()
    pipeline = [
        {"$match": {"logged_at": {"$gte": since}}},
        {"$group": {
            "_id": "$vertical",
            "messages_sent":     {"$sum": 1},
            "manual_cost_total": {"$sum": "$manual_cost_ngn"},
            "api_cost_total":    {"$sum": "$api_cost_ngn"},
            "value_generated":   {"$sum": "$value_generated_ngn"},
        }},
        {"$sort": {"value_generated": -1}},
    ]
    return [
        {
            "vertical": r["_id"],
            "messages_sent": r["messages_sent"],
            "manual_equivalent_ngn": r["manual_cost_total"],
            "api_cost_ngn": r["api_cost_total"],
            "value_generated_ngn": r["value_generated"],
        }
        for r in col.aggregate(pipeline)
    ]
