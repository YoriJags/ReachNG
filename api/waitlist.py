"""
Waitlist API.

Public:
  POST /api/v1/waitlist           — join the waitlist
  GET  /api/v1/waitlist/counter   — public total + top verticals (for landing tile)
  GET  /waitlist                  — the form page

Admin (Basic Auth):
  GET  /api/v1/admin/waitlist                  — full list
  POST /api/v1/admin/waitlist/{position}/invite — mark a person as invited
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from auth import require_auth as _admin_auth
from services.waitlist import (
    add_to_waitlist, waitlist_total, waitlist_public_counter,
    list_waitlist, mark_invited,
)

router = APIRouter(tags=["Waitlist"])


# ─── Public ──────────────────────────────────────────────────────────────────

class WaitlistJoin(BaseModel):
    name:          str = Field(..., min_length=1, max_length=80)
    business_name: str = Field(..., min_length=1, max_length=120)
    vertical:      str = Field(..., min_length=1, max_length=32)
    phone:         Optional[str] = Field(None, max_length=24)
    email:         Optional[str] = Field(None, max_length=120)
    city:          Optional[str] = Field(None, max_length=60)
    brief_pain:    Optional[str] = Field(None, max_length=600)
    source:        Optional[str] = Field(None, max_length=32)
    # Pilot-application qualifying fields (2026-05-17)
    enquiry_volume:           Optional[str]       = Field(None, max_length=12)
    avg_deal_value:           Optional[str]       = Field(None, max_length=12)
    top_pains:                Optional[list[str]] = Field(None, max_length=8)
    trust_ai_draft:           Optional[str]       = Field(None, max_length=12)
    sample_customer_message:  Optional[str]       = Field(None, max_length=1200)


@router.post("/api/v1/waitlist")
async def public_join(payload: WaitlistJoin):
    try:
        doc = add_to_waitlist(
            name=payload.name,
            business_name=payload.business_name,
            vertical=payload.vertical,
            phone=payload.phone,
            email=payload.email,
            city=payload.city,
            brief_pain=payload.brief_pain,
            source=payload.source,
            enquiry_volume=payload.enquiry_volume,
            avg_deal_value=payload.avg_deal_value,
            top_pains=payload.top_pains,
            trust_ai_draft=payload.trust_ai_draft,
            sample_customer_message=payload.sample_customer_message,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "position":      doc["position"],
        "business_name": doc["business_name"],
        "total_on_list": waitlist_total(),
        "message":       f"Application received for {doc['business_name']}. EYO will WhatsApp you within 24-48h with a tailored demo.",
    }


@router.get("/api/v1/waitlist/counter")
async def public_counter():
    return waitlist_public_counter()


@router.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page(request: Request, vertical: Optional[str] = None):
    """Render the public waitlist form. `vertical` query param pre-selects."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "marketing/waitlist.html", {
        "preselected_vertical": (vertical or "").lower(),
        "total":                waitlist_total(),
    })


# ─── Admin ───────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/waitlist")
async def admin_list(only_uninvited: bool = False, vertical: Optional[str] = None,
                      limit: int = 200, _: str = Depends(_admin_auth)):
    return {"entries": list_waitlist(limit=limit, vertical=vertical, only_uninvited=only_uninvited),
            "total":   waitlist_total()}


@router.post("/api/v1/admin/waitlist/{position}/invite")
async def admin_invite(position: int, _: str = Depends(_admin_auth)):
    ok = mark_invited(position)
    if not ok:
        raise HTTPException(404, "position not found")
    return {"position": position, "invited": True}
