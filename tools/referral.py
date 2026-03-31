"""
Referral chain tracking — records which client referred another client.
Tracks referral rewards and conversion status.
"""
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from pymongo import ASCENDING, DESCENDING


def get_referral_collection():
    return get_db()["referrals"]


def ensure_referral_indexes():
    col = get_referral_collection()
    col.create_index([("referrer_client_name", ASCENDING)])
    col.create_index([("referred_client_name", ASCENDING)])
    col.create_index([("status", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])


def record_referral(
    referrer_client_name: str,
    referred_client_name: str,
    notes: str | None = None,
) -> str:
    """Log a new referral. Status starts as 'pending'."""
    result = get_referral_collection().insert_one({
        "referrer_client_name": referrer_client_name,
        "referred_client_name": referred_client_name,
        "status": "pending",        # pending | converted | rewarded
        "reward_months_free": 1,    # Referrer gets 1 month free on conversion
        "notes": notes,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def convert_referral(referral_id: str) -> bool:
    """Mark a referral as converted (referred client became paying)."""
    result = get_referral_collection().update_one(
        {"_id": ObjectId(referral_id)},
        {"$set": {
            "status": "converted",
            "converted_at": datetime.now(timezone.utc),
        }},
    )
    return result.modified_count > 0


def reward_referral(referral_id: str) -> bool:
    """Mark referral reward as issued to the referrer."""
    result = get_referral_collection().update_one(
        {"_id": ObjectId(referral_id)},
        {"$set": {
            "status": "rewarded",
            "rewarded_at": datetime.now(timezone.utc),
        }},
    )
    return result.modified_count > 0


def get_referral_stats() -> dict:
    """Summary of referral pipeline."""
    col = get_referral_collection()
    total     = col.count_documents({})
    pending   = col.count_documents({"status": "pending"})
    converted = col.count_documents({"status": "converted"})
    rewarded  = col.count_documents({"status": "rewarded"})
    return {
        "total": total,
        "pending": pending,
        "converted": converted,
        "rewarded": rewarded,
        "conversion_rate": round((converted / total) * 100, 1) if total else 0,
    }


def list_referrals(referrer: str | None = None) -> list[dict]:
    query = {}
    if referrer:
        query["referrer_client_name"] = referrer
    docs = list(get_referral_collection().find(query).sort("created_at", -1))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs
