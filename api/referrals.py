from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from tools.referral import record_referral, convert_referral, reward_referral, get_referral_stats, list_referrals

router = APIRouter(prefix="/referrals", tags=["Referrals"])


class ReferralCreate(BaseModel):
    referrer_client_name: str
    referred_client_name: str
    notes: Optional[str] = None


@router.post("/")
async def create_referral(body: ReferralCreate):
    ref_id = record_referral(
        referrer_client_name=body.referrer_client_name,
        referred_client_name=body.referred_client_name,
        notes=body.notes,
    )
    return {"success": True, "referral_id": ref_id}


@router.post("/{referral_id}/convert")
async def convert(referral_id: str):
    ok = convert_referral(referral_id)
    if not ok:
        raise HTTPException(404, "Referral not found")
    return {"success": True, "status": "converted"}


@router.post("/{referral_id}/reward")
async def reward(referral_id: str):
    ok = reward_referral(referral_id)
    if not ok:
        raise HTTPException(404, "Referral not found")
    return {"success": True, "status": "rewarded"}


@router.get("/stats")
async def stats():
    return get_referral_stats()


@router.get("/")
async def list_all(referrer: Optional[str] = None):
    return list_referrals(referrer=referrer)
