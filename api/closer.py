"""
ReachNG Closer API — Phase 1 intake + lead management.

Three intake channels:
  A) Email forward (stub — DNS/SPF not ready on reachng.ng yet)
  B) Unipile WhatsApp inbound — wired in api/webhooks.py
  C) Webhook: POST /closer/leads/{token} — for CRM/form integration

Admin-only brief edits. Portal read-only in Phase 1.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from bson import ObjectId

from database import get_db
from services.closer import (
    CloserBrief,
    create_lead,
    list_leads_for_client,
    get_lead,
    update_brief,
    update_stage,
    append_thread_message,
    VALID_STAGES,
)

# Admin-only router (Basic Auth) — brief edits, cross-client lead mgmt
router = APIRouter(prefix="/closer", tags=["Closer"])

# Public router — token-gated intake + portal reads. NO Basic Auth.
public_router = APIRouter(prefix="/closer", tags=["Closer Public"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_client_by_token(token: str) -> dict:
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    return client


def _get_client_by_name(name: str) -> dict:
    client = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")
    return client


def _enforce_real_estate(client: dict) -> None:
    if client.get("vertical") != "real_estate":
        raise HTTPException(400, "Closer is real-estate only in Phase 1")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LeadIntakePayload(BaseModel):
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    inquiry_text: str = ""
    source_consent: Optional[str] = Field(
        None,
        description="'form', 'inbound', 'explicit' — lawful-basis tag for this lead",
    )


class BriefPayload(BaseModel):
    product: str = ""
    icp: str = ""
    qualifying_questions: list[str] = []
    red_flags: list[str] = []
    closing_action: str = ""
    tone: str = "warm-professional"
    pricing_rules: str = ""
    never_say: list[str] = []


class StagePayload(BaseModel):
    stage: Literal["new", "qualifying", "ready", "booked", "lost", "stalled"]
    handover: bool = False


class NotePayload(BaseModel):
    body: str
    author: Optional[str] = None


class EmailIntakePayload(BaseModel):
    """Stub — email-forward intake. Wire to reachng.ng catch-all once DNS is sorted."""
    to: str = Field(..., description="e.g. 'leads-{token}@reachng.ng'")
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    subject: str = ""
    body: str = ""


# ─── Intake channel C — Webhook ───────────────────────────────────────────────

@public_router.post("/leads/{token}", status_code=201)
async def closer_webhook_intake(token: str, payload: LeadIntakePayload):
    """Channel C: CRM / form integration posts JSON here. Token = client portal_token."""
    client = _get_client_by_token(token)
    _enforce_real_estate(client)
    if not (payload.contact_phone or payload.contact_email or payload.inquiry_text):
        raise HTTPException(400, "Provide at least one of: contact_phone, contact_email, inquiry_text")

    lead = create_lead(
        client_id=str(client["_id"]),
        client_name=client["name"],
        vertical=client.get("vertical", "real_estate"),
        source="webhook",
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        inquiry_text=payload.inquiry_text,
        source_consent=payload.source_consent or "inbound",
    )
    return {"success": True, "lead": lead}


# ─── Intake channel A — Email parser (STUB) ───────────────────────────────────

@public_router.post("/leads/email", status_code=201)
async def closer_email_intake(payload: EmailIntakePayload):
    """
    Channel A (STUB): parse inbound email, extract token from `leads-{token}@reachng.ng`.

    Blocker: reachng.ng domain SPF/DKIM and catch-all mailbox not set up yet.
    Endpoint exists so the parser and downstream flow can be tested with fixture payloads.
    Hook up a real MX forwarder (Cloudflare Email Routing / SendGrid Inbound Parse) when ready.
    """
    m = re.match(r"^\s*leads-([A-Za-z0-9_\-]+)@reachng\.ng\s*$", payload.to, re.IGNORECASE)
    if not m:
        raise HTTPException(400, "Invalid 'to' address — expected leads-{token}@reachng.ng")
    token = m.group(1)
    client = _get_client_by_token(token)
    _enforce_real_estate(client)

    inquiry = (payload.subject + "\n\n" + payload.body).strip()
    lead = create_lead(
        client_id=str(client["_id"]),
        client_name=client["name"],
        vertical=client.get("vertical", "real_estate"),
        source="email",
        contact_name=payload.from_name,
        contact_email=payload.from_email,
        inquiry_text=inquiry,
        source_consent="inbound",
    )
    return {"success": True, "lead": lead}


# ─── Brief management (admin) ─────────────────────────────────────────────────

@router.get("/clients/{name}/brief")
async def get_client_brief(name: str):
    client = _get_client_by_name(name)
    _enforce_real_estate(client)
    return {
        "client": client["name"],
        "closer_enabled": client.get("closer_enabled", False),
        "brief": client.get("closer_brief", {}),
    }


@router.put("/clients/{name}/brief")
async def set_client_brief(name: str, payload: BriefPayload):
    client = _get_client_by_name(name)
    _enforce_real_estate(client)
    brief = CloserBrief(**payload.model_dump())
    result = update_brief(str(client["_id"]), brief)
    return {"success": True, "client": client["name"], **result}


# ─── Lead read / list ─────────────────────────────────────────────────────────

@router.get("/clients/{name}/leads")
async def list_client_leads(name: str, stage: Optional[str] = None, limit: int = 100):
    client = _get_client_by_name(name)
    _enforce_real_estate(client)
    if stage and stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage '{stage}'. Valid: {VALID_STAGES}")
    leads = list_leads_for_client(str(client["_id"]), stage=stage, limit=limit)
    return {"client": client["name"], "count": len(leads), "leads": leads}


@router.get("/leads/by-id/{lead_id}")
async def get_single_lead(lead_id: str):
    try:
        ObjectId(lead_id)
    except Exception:
        raise HTTPException(400, "Invalid lead_id")
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


# ─── Lead mutations ───────────────────────────────────────────────────────────

@router.patch("/leads/by-id/{lead_id}/stage")
async def patch_stage(lead_id: str, payload: StagePayload):
    try:
        ObjectId(lead_id)
    except Exception:
        raise HTTPException(400, "Invalid lead_id")
    ok = update_stage(lead_id, payload.stage, handover=payload.handover)
    if not ok:
        raise HTTPException(404, "Lead not found")
    return {"success": True, "lead_id": lead_id, "stage": payload.stage}


@router.post("/leads/by-id/{lead_id}/note")
async def add_note(lead_id: str, payload: NotePayload):
    try:
        ObjectId(lead_id)
    except Exception:
        raise HTTPException(400, "Invalid lead_id")
    ok = append_thread_message(
        lead_id,
        direction="note",
        channel="admin",
        body=payload.body,
        author=payload.author,
    )
    if not ok:
        raise HTTPException(404, "Lead not found")
    return {"success": True, "lead_id": lead_id}


# ─── Dry run (admin-only test intake) ─────────────────────────────────────────

class DryRunPayload(BaseModel):
    contact_name: Optional[str] = "Test Buyer"
    contact_phone: Optional[str] = "+2348000000000"
    contact_email: Optional[str] = None
    inquiry_text: str = (
        "Hi, saw your 3-bed terrace listing in Lekki Phase 1. "
        "Is it still available? What's the price range and is it freehold?"
    )
    source: Literal["email", "whatsapp", "webhook", "manual"] = "manual"


@router.post("/dry-run/{name}", status_code=201)
async def closer_dry_run(name: str, payload: Optional[DryRunPayload] = None):
    """Create a synthetic lead against a client so you can walk the flow end-to-end.

    Shows up in both the admin Closer inbox and the client portal Closer Inbox tab.
    Safe to call repeatedly — every call produces a fresh lead.
    """
    client = _get_client_by_name(name)
    _enforce_real_estate(client)
    p = payload or DryRunPayload()
    lead = create_lead(
        client_id=str(client["_id"]),
        client_name=client["name"],
        vertical="real_estate",
        source=p.source,
        contact_name=p.contact_name,
        contact_phone=p.contact_phone,
        contact_email=p.contact_email,
        inquiry_text=p.inquiry_text,
        source_consent="dry_run",
    )
    return {"success": True, "dry_run": True, "lead": lead}


# ─── Portal-scoped read (client-side, token-gated) ────────────────────────────

@public_router.get("/portal/{token}/leads")
async def portal_list_leads(token: str, stage: Optional[str] = None, limit: int = 100):
    """Read-only listing used by the client portal Closer Inbox tab."""
    client = _get_client_by_token(token)
    _enforce_real_estate(client)
    if stage and stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage '{stage}'. Valid: {VALID_STAGES}")
    leads = list_leads_for_client(str(client["_id"]), stage=stage, limit=limit)
    return {"client": client["name"], "count": len(leads), "leads": leads}


@public_router.get("/portal/{token}/leads/{lead_id}")
async def portal_get_lead(token: str, lead_id: str):
    client = _get_client_by_token(token)
    _enforce_real_estate(client)
    try:
        ObjectId(lead_id)
    except Exception:
        raise HTTPException(400, "Invalid lead_id")
    lead = get_lead(lead_id)
    if not lead or lead.get("client_id") != str(client["_id"]):
        raise HTTPException(404, "Lead not found")
    return lead
