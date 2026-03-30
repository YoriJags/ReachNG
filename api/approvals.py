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
