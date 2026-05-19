"""
Waitlist API.

Public:
  POST /api/v1/waitlist
  GET  /api/v1/waitlist/counter
  GET  /waitlist

Admin (Basic Auth):
  GET  /api/v1/admin/waitlist
  POST /api/v1/admin/waitlist/{position}/invite
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
from services.analytics import (
    track_page_viewed, track_waitlist_joined, track_waitlist_invite_sent,
)

router = APIRouter(tags=["Waitlist"])


class WaitlistJoin(BaseModel):
    name:          str = Field(..., min_length=1, max_length=80)
    business_name: str = Field(..., min_length=1, max_length=120)
    vertical:      str = Field(..., min_length=1, max_length=32)
    phone:         Optional[str] = Field(None, max_length=24)
    email:         Optional[str] = Field(None, max_length=120)
    city:          Optional[str] = Field(None, max_length=60)
    brief_pain:    Optional[str] = Field(None, max_length=600)
    source:        Optional[str] = Field(None, max_length=32)
    enquiry_volume:          Optional[str]       = Field(None, max_length=12)
    avg_deal_value:          Optional[str]       = Field(None, max_length=12)
    top_pains:               Optional[list[str]] = Field(None, max_length=8)
    trust_ai_draft:          Optional[str]       = Field(None, max_length=12)
    sample_customer_message: Optional[str]       = Field(None, max_length=1200)


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

    total = waitlist_total()
    track_waitlist_joined(
        email=payload.email, phone=payload.phone,
        position=doc["position"], vertical=payload.vertical,
        city=payload.city, source=payload.source,
        enquiry_volume=payload.enquiry_volume,
        avg_deal_value=payload.avg_deal_value,
        trust_ai_draft=payload.trust_ai_draft,
        top_pains=payload.top_pains,
        has_pain=bool(payload.brief_pain),
        has_sample_message=bool(payload.sample_customer_message),
        total_on_list=total,
    )
    return {
        "position":      doc["position"],
        "business_name": doc["business_name"],
        "total_on_list": total,
        "message":       "You're on the early access list. Based on your answers, we may invite you into the first pilot batch.",
    }


@router.get("/api/v1/waitlist/counter")
async def public_counter():
    return waitlist_public_counter()


@router.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page(request: Request, vertical: Optional[str] = None):
    templates = request.app.state.templates
    track_page_viewed(
        page="waitlist", path="/waitlist",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_campaign=request.query_params.get("utm_campaign"),
        preselected_vertical=(vertical or "").lower(),
    )
    return templates.TemplateResponse(request, "marketing/waitlist.html", {
        "preselected_vertical": (vertical or "").lower(),
        "total":                waitlist_total(),
    })


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
    track_waitlist_invite_sent(position=position, total_on_list=waitlist_total())
    return {"position": position, "invited": True}
