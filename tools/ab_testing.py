"""
A/B/C message testing — tracks which message variant was sent per contact
and compares reply rates across variants.

Variants are A/B/C. For the ReachNG pre-launch founder outreach they map to
three angles (see services/reachng_self_outreach.VARIANT_STYLES):
    A → founder/direct    B → money-leak    C → owner-relief
Older 2-variant campaigns that only ever produced A/B still work unchanged.
"""
import random
from datetime import datetime, timezone, timedelta
from database import get_db
from pymongo import ASCENDING, DESCENDING

# The full variant set. Kept in one place so the drafter, the runner, and the
# stats reader never drift out of sync.
VARIANTS = ("A", "B", "C")


def get_ab_collection():
    return get_db()["ab_tests"]


def ensure_ab_indexes():
    col = get_ab_collection()
    col.create_index([("vertical", ASCENDING)])
    col.create_index([("variant", ASCENDING)])
    col.create_index([("contact_id", ASCENDING)])
    col.create_index([("sent_at", DESCENDING)])


def assign_variant() -> str:
    """Randomly assign one variant with equal probability across A/B/C."""
    return random.choice(VARIANTS)


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
    for variant in VARIANTS:
        r = rows.get(variant, {"sent": 0, "replied": 0})
        sent    = r["sent"]
        replied = r["replied"]
        result[variant] = {
            "sent": sent,
            "replied": replied,
            "reply_rate": round((replied / sent) * 100, 1) if sent else 0,
        }

    # Winner = highest reply rate among variants that actually sent. Ties (incl.
    # the all-zero cold start) report "tie" so we never crown a phantom winner.
    contenders = [(v, result[v]["reply_rate"]) for v in VARIANTS if result[v]["sent"] > 0]
    if not contenders:
        result["winner"] = "tie"
    else:
        best_rate = max(rate for _, rate in contenders)
        leaders = [v for v, rate in contenders if rate == best_rate]
        result["winner"] = leaders[0] if len(leaders) == 1 else "tie"

    result["period_days"] = days
    return result
