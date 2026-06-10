"""
HITL Approvals API — owner reviews and approves outreach drafts before sending.
This is the kill switch. Nothing goes out without a human tap.
"""
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from bson import ObjectId
from tools.hitl import (
    get_pending, approve_draft, skip_draft, edit_draft,
    get_approval_stats, ApprovalStatus,
)
from tools.roi import log_roi_event
from tools.outreach import send_whatsapp_for_client, send_email
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
    # Capture the original BEFORE edit_draft mutates the doc, for the Learning Card.
    original = ""
    try:
        from database import get_db
        from bson import ObjectId
        _pre = get_db()["pending_approvals"].find_one({"_id": ObjectId(approval_id)}, {"message": 1, "vertical": 1, "client_name": 1, "contact_name": 1})
        original = (_pre or {}).get("message", "")
    except Exception:
        _pre = None

    draft = edit_draft(approval_id, payload.new_message)
    if not draft:
        raise HTTPException(404, "Approval not found")

    background_tasks.add_task(_send_approved, draft)

    # Instant Learning Card — what EYO just learned from this edit.
    learned = None
    try:
        from services.learning_card import instant_insight, record_card
        learned = await instant_insight(original, payload.new_message, (draft.get("vertical") or (_pre or {}).get("vertical")))
        if learned:
            record_card(draft.get("client_name") or (_pre or {}).get("client_name", ""),
                        learned, draft.get("contact_name", ""))
    except Exception:
        learned = None

    return {"success": True, "status": "edited_and_sent",
            "contact": draft["contact_name"], "learned": learned}


@router.post("/{approval_id}/skip")
async def skip(approval_id: str):
    """Skip this draft — it will not be sent."""
    _validate_id(approval_id)
    draft = skip_draft(approval_id)
    if not draft:
        raise HTTPException(404, "Approval not found")
    return {"success": True, "status": "skipped", "contact": draft["contact_name"]}


def _filter_pending(pending: list[dict],
                    client: str | None,
                    confidence: str | None) -> list[dict]:
    """Apply optional per-client / per-confidence filters to a pending list."""
    out = pending
    if client:
        out = [d for d in out if (d.get("client_name") or "").lower() == client.lower()]
    if confidence:
        wanted = confidence.lower()
        out = [d for d in out if ((d.get("risk") or {}).get("confidence") == wanted)]
    return out


@router.post("/approve-all")
async def approve_all(
    background_tasks: BackgroundTasks,
    vertical: str | None = None,
    client: str | None = None,
    confidence: str | None = None,
):
    """Bulk-approve pending drafts. Optional filters: vertical / client / confidence (high|medium|low)."""
    pending = _filter_pending(get_pending(vertical=vertical), client, confidence)
    for draft in pending:
        approved = approve_draft(str(draft["_id"]))
        if approved:
            background_tasks.add_task(_send_approved, approved)
    return {"success": True, "approved_count": len(pending),
            "filters": {"vertical": vertical, "client": client, "confidence": confidence}}


@router.post("/skip-all")
async def skip_all(
    vertical: str | None = None,
    client: str | None = None,
    confidence: str | None = None,
):
    """Bulk-skip pending drafts. Same filters as approve-all."""
    pending = _filter_pending(get_pending(vertical=vertical), client, confidence)
    for draft in pending:
        skip_draft(str(draft["_id"]))
    return {"success": True, "skipped_count": len(pending),
            "filters": {"vertical": vertical, "client": client, "confidence": confidence}}


# ─── Per-draft regenerate ────────────────────────────────────────────────────

_REGEN_STYLES = {"shorter", "warmer", "firmer", "more_specific"}

_REGEN_INSTRUCTIONS = {
    "shorter":       "Rewrite this WhatsApp reply to be roughly half as long. Cut filler words and pleasantries. Keep the substance and tone intact. Do NOT add new information.",
    "warmer":        "Rewrite this WhatsApp reply with a warmer, more personal tone — but stay professional. Lagos premium business voice. No fake endearments (no babe/love/dear). Keep facts identical.",
    "firmer":        "Rewrite this WhatsApp reply to be firmer and more direct. Drop hedging. Set clear expectations. Stay polite — never rude. Keep facts identical.",
    "more_specific": "Rewrite this WhatsApp reply to be more specific where it was vague. Replace 'soon' / 'shortly' / 'as discussed' with concrete times, amounts, or details if you can infer them from context. Otherwise leave a clear placeholder.",
}


@router.post("/{approval_id}/regenerate")
async def regenerate_draft_route(approval_id: str, style: str = "shorter"):
    """Rewrite a pending draft in a chosen style (shorter / warmer / firmer / more_specific).

    Updates the same approval doc in-place — no new HITL row, no schema
    change. Risk score is recomputed against the new text.
    """
    _validate_id(approval_id)
    if style not in _REGEN_STYLES:
        raise HTTPException(400, f"Invalid style. Choose: {sorted(_REGEN_STYLES)}")

    from database import get_db
    from bson import ObjectId
    col = get_db()["pending_approvals"]
    doc = col.find_one({"_id": ObjectId(approval_id)})
    if not doc:
        raise HTTPException(404, "Approval not found")
    if doc.get("status") != "pending":
        raise HTTPException(400, f"Cannot regenerate — draft is already {doc.get('status')}")

    current = doc.get("edited_message") or doc.get("message") or ""
    if not current.strip():
        raise HTTPException(400, "Draft is empty — nothing to regenerate")

    # Single Haiku rewrite. Cheap (~₦2), source-agnostic.
    try:
        import anthropic
        from config import get_settings
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
        client_anth = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client_anth.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            temperature=0.4,
            system=_REGEN_INSTRUCTIONS[style] + "\n\nOutput ONLY the rewritten reply text. No preamble, no quotes, no commentary.",
            messages=[{"role": "user", "content": current}],
        )
        new_text = "".join(b.text for b in resp.content
                            if getattr(b, "type", None) == "text").strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Regenerate failed: {e}")

    # Tone scrub + recompute risk against the new text
    try:
        from tools.tone import scrub_endearments
        new_text = scrub_endearments(new_text)
    except Exception:
        pass
    try:
        from services.draft_risk import score_draft
        new_risk = score_draft(
            message=new_text,
            classification=doc.get("classification"),
            inbound_context=doc.get("inbound_context"),
            vertical=doc.get("vertical"),
            escalated=bool(doc.get("escalated")),
        )
    except Exception:
        new_risk = doc.get("risk")

    col.update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {"message": new_text,
                  "edited_message": None,
                  "risk": new_risk,
                  "regen_style": style,
                  "regen_at": datetime.now(timezone.utc)}},
    )
    return {"success": True, "approval_id": approval_id, "style": style,
            "message": new_text, "risk": new_risk}


# ─── Internal sender ──────────────────────────────────────────────────────────

async def _send_approved(draft: dict):
    """Send a draft that has been approved. Records outreach + ROI."""
    try:
        channel  = draft["channel"]
        message  = draft.get("edited_message") or draft["message"]
        contact_id = str(draft["contact_id"])

        if channel == "whatsapp" and draft.get("phone"):
            # Route by the CLIENT's provider so a Unipile client's reply sends
            # from their connected number — never from ReachNG's own number.
            client_doc = {}
            cname = draft.get("client_name")
            if cname:
                from database import get_db
                client_doc = get_db()["clients"].find_one(
                    {"name": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}}
                ) or {}
            result = await send_whatsapp_for_client(
                phone=draft["phone"], message=message, client_doc=client_doc
            )
        elif channel == "email" and draft.get("email"):
            # Self-outreach campaigns (Client #0) need force_smtp=True so the
            # send routes through hello@reachng.ng via Resend rather than the
            # client's connected mailbox. Detect by source.
            _force = (draft.get("source") in ("closer", "maps", "byo_leads", "social", "signal"))
            cname = draft.get("client_name")
            client_doc = {}
            if cname:
                from database import get_db
                client_doc = get_db()["clients"].find_one(
                    {"name": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}}
                ) or {}
            subject = draft.get("subject", f"Quick question for {draft['contact_name']}")
            # A client's own reply sends FROM their connected mailbox (IMAP/SMTP),
            # not from ReachNG — closes the email loop. Falls back to Resend.
            if not _force and client_doc.get("email_provider") == "imap":
                from services.email_imap import send_email_via_client
                ok = send_email_via_client(client_doc, to_email=draft["email"],
                                           subject=subject, body=message)
                result = {"success": ok, "provider": "client_smtp"}
            else:
                result = await send_email(to_email=draft["email"], subject=subject,
                                          body=message, force_smtp=_force)
        elif channel in ("instagram", "messenger") and draft.get("contact_id"):
            # Reply to an IG/Messenger DM from the client's own Page/IG.
            cname = draft.get("client_name")
            client_doc = {}
            if cname:
                from database import get_db
                client_doc = get_db()["clients"].find_one(
                    {"name": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}}
                ) or {}
            from services.meta_messaging import send_message_for_client
            ok = await send_message_for_client(
                client_doc, channel, recipient_id=str(draft["contact_id"]), text=message)
            result = {"success": ok, "provider": "meta"}
        else:
            log.warning("approved_draft_no_channel", draft_id=str(draft["_id"]))
            return

        # No silent success: require an explicit success flag. On failure, log
        # loudly, mark the draft, and DO NOT record it as sent.
        if not result.get("success"):
            log.error("approved_draft_send_failed", contact=draft.get("contact_name"),
                      channel=channel, detail=result)
            try:
                from database import get_db
                get_db()["pending_approvals"].update_one(
                    {"_id": draft["_id"]},
                    {"$set": {"send_failed": True,
                              "send_error": result.get("error") or "unknown",
                              "send_failed_at": datetime.now(timezone.utc)}},
                )
            except Exception:
                pass
            return

        if result.get("success"):
            # Extract the /hi/{slug} from the body so we can attribute the
            # eventual click/open back to this row.
            slug_match = re.search(r"www\.reachng\.ng/hi/([a-z0-9]+)", message or "")
            outreach_slug = slug_match.group(1) if slug_match else None
            record_outreach(
                contact_id=contact_id,
                channel=channel,
                message=message,
                attempt_number=1,
                client_name=draft.get("client_name"),
                subject=draft.get("subject"),
                to_email=draft.get("email"),
                to_phone=draft.get("phone"),
                provider_message_id=result.get("message_id") or result.get("id"),
                outreach_slug=outreach_slug,
                # Self-outreach (b2b_saas) follows the v2 drip cadence: touch 2
                # ~3 days after this first touch.
                followup_in_days=3 if draft.get("vertical") == "b2b_saas" else None,
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
