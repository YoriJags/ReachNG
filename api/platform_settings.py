"""
Platform Settings API — operator-only Control Tower endpoints.

Surfaces:
  GET  /api/v1/admin/pricing            → current pricing dict + audit tail
  POST /api/v1/admin/pricing            → set new pricing (validated)
  GET  /api/v1/admin/settings/{key}     → generic get for any setting
  POST /api/v1/admin/settings/{key}     → generic set
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth as _admin_auth
from services.platform_settings import (
    get_plan_pricing, set_plan_pricing, get_pricing_audit,
    get_setting, set_setting,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Platform Settings"])


# ─── Pricing ──────────────────────────────────────────────────────────────────

class PricingPayload(BaseModel):
    starter: dict = Field(..., description="{label, ngn}")
    growth:  dict = Field(..., description="{label, ngn}")
    scale:   dict = Field(..., description="{label, ngn}")


@router.get("/pricing")
async def admin_get_pricing(_: str = Depends(_admin_auth)):
    return {
        "pricing": get_plan_pricing(),
        "audit":   get_pricing_audit(limit=20),
    }


@router.post("/pricing")
async def admin_set_pricing(payload: PricingPayload, _: str = Depends(_admin_auth)):
    try:
        result = set_plan_pricing(payload.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


# ─── Generic settings get/set ─────────────────────────────────────────────────

class SettingBody(BaseModel):
    value: Any


@router.get("/settings/{key}")
async def admin_get_setting(key: str, _: str = Depends(_admin_auth)):
    return {"key": key, "value": get_setting(key)}


@router.post("/settings/{key}")
async def admin_set_setting(key: str, body: SettingBody, _: str = Depends(_admin_auth)):
    return set_setting(key, body.value)
