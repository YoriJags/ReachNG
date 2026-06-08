"""
Traction API — the North-Star scoreboard (docs/NORTH_STAR.md, C4).

One admin endpoint: whole-book roll-up of ₦ recovered, retention, channel mix,
and HITL throughput. Read-only aggregation; the founder's traction/fundraising
pane and the acquisition scoreboard in one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_auth as _admin_auth
from services.traction import traction_summary

router = APIRouter(prefix="/api/v1/admin/traction", tags=["Traction"])


@router.get("")
async def admin_traction(days: int = 30, _: str = Depends(_admin_auth)):
    return traction_summary(days=days)
