from fastapi import APIRouter
from typing import Optional
from tools.ab_testing import get_ab_stats, mark_ab_replied

router = APIRouter(prefix="/ab", tags=["A/B Testing"])


@router.get("/stats")
async def ab_stats(vertical: Optional[str] = None, days: int = 30):
    """Compare reply rates for variant A vs B."""
    return get_ab_stats(vertical=vertical, days=days)


@router.post("/replied/{contact_id}")
async def record_reply(contact_id: str):
    """Mark the A/B variant sent to this contact as replied."""
    mark_ab_replied(contact_id)
    return {"success": True}
