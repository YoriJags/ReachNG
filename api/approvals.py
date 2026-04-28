"""
HITL Approvals API — owner reviews and approves outreach drafts before sending.
This is the kill switch. Nothing goes out without a human tap.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from bson import ObjectId
from tools.hitl import (
    get_pending, approve_draft, skip_draft, edit_draft,
    get_approval_stats, ApprovalStatus,
)
from tools.roi import log_roi_event
from tools.outreach import send_whatsapp, send_email
from tools.memory import record_outreach, upsert_contact
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if "contact_id" in doc:
        doc["contact_id"] = str(doc["contact_id"])
    return doc


class EditPayload(BaseModel):
    new_message: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_pending(vertical: str | None = None):
    """List all drafts waiting for approval."""
    pending = get_pending(vertical=vertical)
    return [_serialise(p) for p in pending]


@router.get("/stats")
async def approval_stats():
    """Counts by status — pending / approved / skipped / edited."""
    return get_approval_stats()


@router.post("/{approval_id}/approve")
async def approve(approval_id: str, background_tasks: BackgroundTasks):
    """
    Approve a draft — sends the message immediately.
    This is the one-tap approval the owner uses.
    """
    _validate_id(approval_id)
    draft = approve_draft(approval_id)
    if not draft:
        raise HTTPException(404, "Approval not found")

    background_tasks.add_task(_send_approved, draft)
    return {"success": True, "status": "approved", "contact": draft["contact_name"]}


@router.post("/{approval_id}/edit")
async def edit_and_approve(approval_id: str, payload: EditPayload, background_tasks: BackgroundTasks):
    """
    Edit the message text and approve — sends the edited version.
    """
    _validate_id(approval_id)
    draft = edit_draft(approval_id, payload.new_message)
    if not draft:
        raise HTTPException(404, "Approval not found")

    background_tasks.add_task(_send_approved, draft)
    return {"success": True, "status": "edited_and_sent", "contact": draft["contact_name"]}


@router.post("/{approval_id}/skip")
async def skip(approval_id: str):
    """Skip this draft — it will not be sent."""
    _validate_id(approval_id)
    draft = skip_draft(approval_id)
    if not draft:
        raise HTTPException(404, "Approval not found")
    return {"success": True, "status": "skipped", "contact": draft["contact_name"]}


@router.post("/approve-all")
async def approve_all(background_tasks: BackgroundTasks, vertical: str | None = None):
    """Approve all pending drafts at once."""
    pending = get_pending(vertical=vertical)
    for draft in pending:
        approved = approve_draft(str(draft["_id"]))
        if approved:
            background_tasks.add_task(_send_approved, approved)
    return {"success": True, "approved_count": len(pending)}


@router.post("/skip-all")
async def skip_all(vertical: str | None = None):
    """Skip all pending drafts."""
    pending = get_pending(vertical=vertical)
    for draft in pending:
        skip_draft(str(draft["_id"]))
    return {"success": True, "skipped_count": len(pending)}


# ─── Internal sender ──────────────────────────────────────────────────────────

async def _send_approved(draft: dict):
    """Send a draft that has been approved. Records outreach + ROI."""
    try:
        channel  = draft["channel"]
        message  = draft.get("edited_message") or draft["message"]
        contact_id = str(draft["contact_id"])

        if channel == "whatsapp" and draft.get("phone"):
            result = await send_whatsapp(phone=draft["phone"], message=message)
        elif channel == "email" and draft.get("email"):
            result = await send_email(
                to_email=draft["email"],
                subject=draft.get("subject", f"Quick question for {draft['contact_name']}"),
                body=message,
            )
        else:
            log.warning("approved_draft_no_channel", draft_id=str(draft["_id"]))
            return

        if result.get("success", True):
            record_outreach(
                contact_id=contact_id,
                channel=channel,
                message=message,
                attempt_number=1,
            )
            log_roi_event(
                contact_name=draft["contact_name"],
                vertical=draft["vertical"],
                channel=channel,
            )
            log.info("approved_draft_sent", contact=draft["contact_name"])

    except Exception as e:
        log.error("approved_draft_send_failed", contact=draft.get("contact_name"), error=str(e))


def _validate_id(approval_id: str):
    try:
        ObjectId(approval_id)
    except Exception:
        raise HTTPException(400, "Invalid approval ID")


# ─── Portal (token-gated) ────────────────────────────────────────────────────
# Clients see + action only their OWN drafts via portal token. No Basic Auth.
import re as _re_approvals
from fastapi import Request
from database import get_db as _get_db_for_approvals

public_router = APIRouter(prefix="/portal-approvals", tags=["Approvals — Portal"])


def _client_by_token(token: str) -> dict:
    client = _get_db_for_approvals()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    return client


def _scope_query_to_client(client_name: str) -> dict:
    """Drafts are scoped by client_name (case-insensitive). Older drafts may
    not have client_name set — those are admin-managed and never returned here,
    which is the safe default for cross-tenant isolation."""
    return {
        "client_name": {"$regex": f"^{_re_approvals.escape(client_name)}$", "$options": "i"},
    }


def _ensure_owns(approval_id: str, client_name: str) -> dict:
    """Look up an approval and confirm it belongs to this token's client.
    Raises 404 (not 403) on mismatch — never reveal that a draft exists for
    a different tenant."""
    _validate_id(approval_id)
    doc = get_approvals().find_one({"_id": ObjectId(approval_id)})
    if not doc:
        raise HTTPException(404, "Approval not found")
    owner = (doc.get("client_name") or "").strip()
    if owner.lower() != client_name.strip().lower():
        raise HTTPException(404, "Approval not found")
    return doc


@public_router.get("/{token}/")
async def portal_list_pending(token: str, vertical: str | None = None):
    """Pending drafts for THIS client only."""
    client = _client_by_token(token)
    name = client.get("name") or ""
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    query = {
        **_scope_query_to_client(name),
        "status": ApprovalStatus.PENDING,
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }
    if vertical:
        query["vertical"] = vertical
    rows = list(get_approvals().find(query).sort("created_at", -1).limit(100))
    return [_serialise(r) for r in rows]


@public_router.get("/{token}/stats")
async def portal_stats(token: str):
    """Per-client approval counts."""
    client = _client_by_token(token)
    name = client.get("name") or ""
    pipeline = [
        {"$match": _scope_query_to_client(name)},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = list(get_approvals().aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


@public_router.post("/{token}/{approval_id}/approve")
async def portal_approve(token: str, approval_id: str, background_tasks: BackgroundTasks):
    client = _client_by_token(token)
    name = client.get("name") or ""
    _ensure_owns(approval_id, name)
    draft = approve_draft(approval_id)
    if not draft:
        raise HTTPException(409, "Approval expired or already actioned")
    background_tasks.add_task(_send_approved, draft)
    return {"success": True, "status": "approved", "contact": draft.get("contact_name")}


@public_router.post("/{token}/{approval_id}/edit")
async def portal_edit_and_approve(
    token: str, approval_id: str, payload: EditPayload, background_tasks: BackgroundTasks
):
    client = _client_by_token(token)
    name = client.get("name") or ""
    _ensure_owns(approval_id, name)
    draft = edit_draft(approval_id, payload.new_message)
    if not draft:
        raise HTTPException(404, "Approval not found")
    background_tasks.add_task(_send_approved, draft)
    return {"success": True, "status": "edited_and_sent", "contact": draft.get("contact_name")}


@public_router.post("/{token}/{approval_id}/skip")
async def portal_skip(token: str, approval_id: str):
    client = _client_by_token(token)
    name = client.get("name") or ""
    _ensure_owns(approval_id, name)
    draft = skip_draft(approval_id)
    if not draft:
        raise HTTPException(404, "Approval not found")
    return {"success": True, "status": "skipped", "contact": draft.get("contact_name")}
