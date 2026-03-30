"""
ROI API — exposes ROI summary and per-vertical breakdown to the dashboard.
"""
from fastapi import APIRouter
from tools.roi import get_roi_summary, get_roi_by_vertical

router = APIRouter(prefix="/roi", tags=["ROI"])


@router.get("/summary")
async def roi_summary(days: int = 30, client_name: str | None = None):
    """Total ROI for the last N days — messages sent, cost saved, ROI %."""
    return get_roi_summary(days=days, client_name=client_name)


@router.get("/by-vertical")
async def roi_by_vertical(days: int = 30):
    """ROI breakdown per vertical for the last N days."""
    return get_roi_by_vertical(days=days)
