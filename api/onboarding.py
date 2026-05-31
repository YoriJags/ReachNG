"""
Self-serve onboarding wizard for ReachNG.

Replaces the manual onboarding call. The founder walks themselves through
7 steps at /portal/{token}/onboard:

  1. Business Basics    → BusinessBrief identity + ICP
  2. Voice & Tone       → BusinessBrief tone_overrides, signature, never_say + KB sample replies
  3. Offer & Pricing    → BusinessBrief products, pricing_rules, payment_terms
  4. Lead Qualification → BusinessBrief qualifying_questions, not_a_fit, red_flags
  5. Approval Rules     → ClientRules + autopilot toggle
  6. Test EYO           → runs a real draft on a customer message the founder pastes
  7. Go-Live Checklist  → verifies completeness, flips approval queue ON, marks onboarded_at

State lives in clients.onboarding_progress = {current_step, completed_steps, started_at, completed_at}.
Each step's "Save & Continue" merges into BusinessBrief via the existing portal_put_brief endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from database import get_db
from services.brief import BusinessBrief, brief_health, get_brief, update_brief
from services.knowledge_base import add_document as kb_add_document

log = structlog.get_logger()
router = APIRouter(tags=["Onboarding Wizard"])


def _clients():
    return get_db()["clients"]


def _get_client_by_token(token: str) -> Optional[dict]:
    return _clients().find_one({"portal_token": token, "active": True})


def _client_id(client: dict) -> str:
    return str(client["_id"])


# ─── Wizard page ─────────────────────────────────────────────────────────────

@router.get("/portal/{token}/onboard", response_class=HTMLResponse)
async def portal_onboard_page(token: str, request: Request):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal/onboard.html", {
        "token":       token,
        "client_name": client.get("name", "your business"),
        "vertical":    (client.get("vertical") or "").replace("_", " ").title(),
    })


# ─── Save step (partial brief merge) ─────────────────────────────────────────

class StepPayload(BaseModel):
    step: int = Field(..., ge=1, le=7)
    data: dict = Field(default_factory=dict)


# Map step number → BusinessBrief field set the client form provides.
# Keeps the endpoint conservative: only whitelisted keys merge into the brief.
_STEP_FIELDS = {
    1: {"trading_name", "one_liner", "geography", "icp"},
    2: {"tone_overrides", "signature", "never_say", "always_say", "language_mix"},
    3: {"products", "pricing_rules", "payment_terms", "availability_notes"},
    4: {"qualifying_questions", "not_a_fit", "red_flags", "closing_action"},
    # Steps 5, 6, 7 don't merge into the brief directly.
}


@router.post("/api/v1/portal/{token}/onboard/step")
async def save_step(token: str, payload: StepPayload):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)

    # Merge whitelisted fields into the brief
    merge_fields = _STEP_FIELDS.get(payload.step, set())
    if merge_fields:
        wrapper = get_brief(client_id=cid) or {}
        current_brief = wrapper.get("business_brief") or {}
        merged = {**current_brief}
        for k in merge_fields:
            if k in payload.data:
                merged[k] = payload.data[k]
        try:
            brief = BusinessBrief(**{k: v for k, v in merged.items() if k in BusinessBrief.model_fields})
            update_brief(brief=brief, client_id=cid)
        except Exception as e:
            log.warning("onboarding_brief_merge_failed", step=payload.step, error=str(e))
            raise HTTPException(400, f"could not save step {payload.step}: {e}")

    # Step 2 also ingests sample-reply examples into the KB
    if payload.step == 2 and payload.data.get("sample_replies"):
        samples = payload.data["sample_replies"]
        if isinstance(samples, str):
            samples = [s.strip() for s in samples.split("\n\n") if s.strip()]
        for i, sample in enumerate(samples[:10]):
            try:
                kb_add_document(
                    client_id=cid,
                    title=f"Sample reply #{i+1}",
                    raw_text=sample,
                    tags=["onboarding_wizard", "voice_sample"],
                )
            except Exception as e:
                log.warning("kb_ingest_failed", error=str(e))

    # Step 5 saves approval rules onto the client doc directly
    if payload.step == 5:
        rules_update = {}
        if "autopilot" in payload.data:
            rules_update["autopilot"] = bool(payload.data["autopilot"])
        if "holding_message" in payload.data:
            rules_update["holding_message"] = (payload.data["holding_message"] or "").strip()[:600]
        if rules_update:
            _clients().update_one({"_id": client["_id"]}, {"$set": rules_update})

    # Update progress
    _clients().update_one(
        {"_id": client["_id"]},
        {
            "$set": {
                "onboarding_progress.current_step": payload.step + 1,
                "onboarding_progress.last_saved_at": datetime.now(timezone.utc),
            },
            "$addToSet": {"onboarding_progress.completed_steps": payload.step},
            "$setOnInsert": {"onboarding_progress.started_at": datetime.now(timezone.utc)},
        },
        upsert=False,
    )

    health = brief_health(client_id=cid) if merge_fields else None
    return {"ok": True, "step": payload.step, "health": health}


# ─── Test EYO draft ──────────────────────────────────────────────────────────

class TestDraftPayload(BaseModel):
    customer_message: str = Field(..., min_length=3, max_length=2000)
    customer_name: Optional[str] = Field(default="Test Customer", max_length=80)


@router.post("/api/v1/portal/{token}/onboard/test-draft")
async def test_draft(token: str, payload: TestDraftPayload):
    """Run a real draft against the saved brief. Returns the drafted reply
    so the founder can edit/approve in the wizard's Step 6."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")

    try:
        from agent.brain import generate_b2c_message
        result = generate_b2c_message(
            customer_name=payload.customer_name or "Test Customer",
            channel="whatsapp",
            vertical=client.get("vertical", "general"),
            client_name=client.get("name"),
            notes=payload.customer_message,
        )
        return {
            "ok": True,
            "draft": result.get("message", ""),
        }
    except Exception as e:
        log.warning("onboarding_test_draft_failed", error=str(e))
        return {"ok": False, "draft": "", "error": str(e)}


# ─── Complete onboarding ─────────────────────────────────────────────────────

@router.post("/api/v1/portal/{token}/onboard/complete")
async def complete_onboarding(token: str):
    """Final step: verify completeness, mark client onboarded, return next step.

    Does NOT flip autopilot — HITL stays on by default. The owner can switch
    Autopilot on per-rule later from the Configure page.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)

    health = brief_health(client_id=cid)
    if not health.get("complete"):
        return {
            "ok":      False,
            "blocked": True,
            "missing": health.get("missing", []),
            "message": "Brief is missing required fields. Go back and complete them.",
        }

    # Check WhatsApp pairing — they need to either connect it or acknowledge they'll do it next
    wa_connected = bool(client.get("whatsapp_account_id"))

    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {
            "onboarded_at":                          datetime.now(timezone.utc),
            "onboarding_progress.completed_at":      datetime.now(timezone.utc),
            "onboarding_progress.current_step":      8,
        }},
    )

    log.info("onboarding_completed", client_id=cid, wa_connected=wa_connected)
    return {
        "ok":              True,
        "wa_connected":    wa_connected,
        "next":            "connect_whatsapp" if not wa_connected else "portal",
    }


# ─── Done-for-You Concierge Setup ────────────────────────────────────────────

class ConciergePayload(BaseModel):
    materials: str = Field(default="", max_length=20000)   # pasted price list / FAQs / sample chats
    links:     list[str] = Field(default_factory=list)
    note:      str = Field(default="", max_length=2000)


@router.post("/api/v1/portal/{token}/concierge")
async def concierge_setup(token: str, payload: ConciergePayload):
    """'Send us your price list, FAQs, voice notes, old chats — we'll train EYO.'

    Premium framing: setup is handled, not homework. We (1) ingest pasted
    materials straight into the knowledge base so EYO can use them, (2) log a
    concierge request for the operator, and (3) ping the operator to action it.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)

    ingested = 0
    if payload.materials.strip():
        try:
            kb_add_document(
                client_id=cid,
                title="Concierge: owner-supplied materials",
                raw_text=payload.materials.strip(),
                tags=["concierge", "owner_supplied"],
            )
            ingested = 1
        except Exception as e:
            log.warning("concierge_kb_ingest_failed", error=str(e))

    try:
        get_db()["concierge_requests"].insert_one({
            "client_id":   cid,
            "client_name": client.get("name"),
            "links":       [l[:300] for l in payload.links[:20]],
            "note":        payload.note.strip(),
            "has_materials": bool(payload.materials.strip()),
            "status":      "new",
            "created_at":  datetime.now(timezone.utc),
        })
    except Exception as e:
        log.warning("concierge_request_log_failed", error=str(e))

    # Best-effort operator ping
    try:
        from services.analytics import track
        track("concierge_setup_requested", distinct_id=f"client:{client.get('name','')}",
              has_materials=bool(payload.materials.strip()), links=len(payload.links))
    except Exception:
        pass

    return {
        "ok": True,
        "ingested_documents": ingested,
        "message": "Got it. EYO is being trained on what you sent — we'll handle the rest and confirm when it's ready.",
    }


# ─── First 24 Hours Win ──────────────────────────────────────────────────────

@router.get("/api/v1/portal/{token}/onboard/first-win")
async def first_win(token: str):
    """Guaranteed useful output within a day — even before WhatsApp is fully
    connected. Runs the money-leak engine on whatever the owner has already
    imported (book, paste, old chats) and returns the dopamine pack:

      • leads to wake up        (rescue targets)
      • payment chases ready    (confirmed collectible)
      • a sample drafted reply  (real draft on their top target)
      • their first Owner Brief preview
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    name = client["name"]

    from services.money_leak import money_leak_report, rescue_targets
    from tools.morning_brief_client import compile_client_brief

    report  = money_leak_report(name)
    targets = rescue_targets(name, days=60, limit=10)

    # One real sample draft on the top revivable conversation, if any.
    sample_draft = ""
    if targets:
        try:
            from agent.brain import generate_b2c_message
            top = targets[0]
            res = generate_b2c_message(
                customer_name=top.get("contact_name") or "there",
                channel="whatsapp",
                vertical=client.get("vertical", "general"),
                client_name=name,
                notes=f"Follow up: {top.get('last_text') or top.get('reason_label')}",
            )
            sample_draft = res.get("message", "")
        except Exception as e:
            log.warning("first_win_sample_draft_failed", error=str(e))

    confirmed = next((c for c in report["categories"] if c["key"] == "confirmed_owed"), {})

    return {
        "ok": True,
        "client": name,
        "headline": report["headline"],
        "leads_to_wake": {"count": len(targets), "sample": targets},
        "payment_chases": {
            "count": confirmed.get("count", 0),
            "amount_ngn": confirmed.get("amount_ngn", 0),
        },
        "sample_draft": sample_draft,
        "brief_preview": compile_client_brief(name, portal_url=f"/portal/{token}"),
        "promise": "By tomorrow morning you'll get this as your first Owner Brief on WhatsApp.",
    }


# ─── Status (for resume) ─────────────────────────────────────────────────────

@router.get("/api/v1/portal/{token}/onboard/status")
async def onboarding_status(token: str):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    cid = _client_id(client)

    progress = client.get("onboarding_progress") or {}
    health   = brief_health(client_id=cid)
    wrapper  = get_brief(client_id=cid) or {}
    brief    = wrapper.get("business_brief") or {}

    return {
        "current_step":     progress.get("current_step", 1),
        "completed_steps":  progress.get("completed_steps", []),
        "started_at":       (progress.get("started_at") or "").__str__() or None,
        "onboarded_at":     (client.get("onboarded_at") or "").__str__() or None,
        "health":           health,
        "wa_connected":     bool(client.get("whatsapp_account_id")),
        "brief":            {k: brief.get(k) for k in BusinessBrief.model_fields.keys() if brief.get(k) is not None},
        "autopilot":        bool(client.get("autopilot", False)),
        "holding_message":  client.get("holding_message", ""),
    }
