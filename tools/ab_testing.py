"""
A/B message testing — tracks which message variant was sent per contact
and compares reply rates between variants A and B.
"""
import random
from datetime import datetime, timezone, timedelta
from database import get_db
from pymongo import ASCENDING, DESCENDING


def get_ab_collection():
    return get_db()["ab_tests"]


def ensure_ab_indexes():
    col = get_ab_collection()
    col.create_index([("vertical", ASCENDING)])
    col.create_index([("variant", ASCENDING)])
    col.create_index([("contact_id", ASCENDING)])
    col.create_index([("sent_at", DESCENDING)])


def assign_variant() -> str:
    """Randomly assign A or B with equal probability."""
    return random.choice(["A", "B"])


def record_ab_send(
    contact_id: str,
    vertical: str,
    channel: str,
    variant: str,
    message: str,
):
    """Log which variant was sent to this contact."""
    get_ab_collection().insert_one({
        "contact_id": contact_id,
        "vertical": vertical,
        "channel": channel,
        "variant": variant,
        "message": message,
        "replied": False,
        "sent_at": datetime.now(timezone.utc),
    })


def mark_ab_replied(contact_id: str):
    """Mark the most recent A/B send for this contact as replied."""
    get_ab_collection().update_one(
        {"contact_id": contact_id},
        {"$set": {"replied": True, "replied_at": datetime.now(timezone.utc)}},
        sort=[("sent_at", DESCENDING)],
    )


def get_ab_stats(vertical: str | None = None, days: int = 30) -> dict:
    """
    Compare reply rates for variant A vs B.
    Returns counts and reply rates per variant.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    match = {"sent_at": {"$gte": since}}
    if vertical:
        match["vertical"] = vertical

    col = get_ab_collection()
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$variant",
            "sent":    {"$sum": 1},
            "replied": {"$sum": {"$cond": ["$replied", 1, 0]}},
        }},
    ]
    rows = {r["_id"]: r for r in col.aggregate(pipeline)}

    result = {}
    for variant in ("A", "B"):
        r = rows.get(variant, {"sent": 0, "replied": 0})
        sent    = r["sent"]
        replied = r["replied"]
        result[variant] = {
            "sent": sent,
            "replied": replied,
            "reply_rate": round((replied / sent) * 100, 1) if sent else 0,
        }

    # Winner
    ra = result["A"]["reply_rate"]
    rb = result["B"]["reply_rate"]
    if ra > rb:
        result["winner"] = "A"
    elif rb > ra:
        result["winner"] = "B"
    else:
        result["winner"] = "tie"

    result["period_days"] = days
    return result
