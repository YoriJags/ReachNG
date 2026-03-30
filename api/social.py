"""
Social signals API — exposes discovered social leads to the dashboard.
"""
from fastapi import APIRouter
from tools.social import get_social_signals, VERTICAL_SOCIAL

router = APIRouter(prefix="/social", tags=["Social"])


@router.get("/signals")
async def social_signals(vertical: str | None = None, limit: int = 50):
    """Recent social leads discovered from Instagram, Twitter, and Facebook."""
    signals = get_social_signals(vertical=vertical, limit=limit)
    return signals


@router.get("/stats")
async def social_stats():
    """Count of social signals found per platform and vertical."""
    from database import get_db
    from datetime import datetime, timezone, timedelta

    col   = get_db()["social_signals"]
    since = datetime.now(timezone.utc) - timedelta(days=7)

    by_platform = list(col.aggregate([
        {"$match": {"found_at": {"$gte": since}}},
        {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
    ]))
    by_vertical = list(col.aggregate([
        {"$match": {"found_at": {"$gte": since}}},
        {"$group": {"_id": "$vertical", "count": {"$sum": 1}}},
    ]))

    return {
        "by_platform": {r["_id"]: r["count"] for r in by_platform},
        "by_vertical": {r["_id"]: r["count"] for r in by_vertical},
        "total_7d":    sum(r["count"] for r in by_platform),
    }
