"""
B2C API — CSV upload + campaign trigger for BYO Leads outreach.

Endpoints:
  POST /b2c/upload/{client_name}         — Upload CSV, import contacts (consent attestation REQUIRED)
  POST /b2c/run/{client_name}            — Run campaign against imported contacts
  GET  /b2c/contacts/{client_name}       — List B2C contacts for a client
  GET  /b2c/stats/{client_name}          — Pipeline stats for B2C contacts
  GET  /b2c/imports/{client_name}        — Audit log of every import + consent attestation
  PATCH /b2c/contacts/{id}/opted-out     — Manual opt-out (NDPR/GDPR)

Compliance + gating:
  - Upload requires explicit consent_attestation=True (lawful basis under NDPR)
  - Each import logs to lead_imports with timestamp/uploader/IP/filename hash
  - Verticals not in BYO_LEADS_ENABLED_VERTICALS are blocked at upload + run
"""
import hashlib
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from database import get_db
from tools.csv_import import (
    parse_and_import_csv, get_b2c_contacts_for_campaign,
    mark_b2c_opted_out, ensure_b2c_indexes, preview_csv,
)
from campaigns.b2c import B2CCampaign
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/b2c", tags=["B2C"])

_MAX_CSV_BYTES = 5 * 1024 * 1024   # 5 MB — enough for 100k rows

# Verticals where BYO Leads is allowed. Recruitment + lending NOT in here on
# purpose — those don't run cold outbound to candidate/borrower lists.
BYO_LEADS_ENABLED_VERTICALS = {
    "real_estate", "legal", "insurance", "fitness",
    "events", "auto", "cooperatives", "general",
}


# Per-vertical CSV templates the client can download. Header names match the
# parser's auto-detect map (phone/whatsapp/mobile, name, email, tags, notes).
_SAMPLE_CSV_BY_VERTICAL: dict[str, str] = {
    "real_estate": (
        "name,phone,email,tags,notes\n"
        "Adaeze Okafor,+2348011112222,adaeze@example.com,walk-in,Inquired about 3-bed Banana terrace\n"
        "Tunde Bello,08022223333,tunde@example.com,referral,Family of 4 relocating from Abuja\n"
        "Emeka Nwosu,+2348033334444,,viewing-march,Saw Eko Atlantic listing\n"
        "Funmi Lawal,+2348044445555,funmi@example.com,past-client,Bought in 2024, asked about new builds\n"
    ),
    "legal": (
        "name,phone,email,tags,notes\n"
        "Chinedu Eze,+2348011112222,chinedu@example.com,past-client,Family law consult 2024\n"
        "Bolanle Adekunle,08022223333,,referral,Property dispute in Lekki\n"
        "Ibrahim Sani,+2348033334444,ibrahim@example.com,enquiry,Asked about retainer terms\n"
    ),
    "insurance": (
        "name,phone,email,tags,notes\n"
        "Kemi Adebayo,+2348011112222,kemi@example.com,renewal,Motor policy expires May\n"
        "Segun Olatunji,08022223333,segun@example.com,family-cover,3 dependents, asked for quote\n"
        "Amaka Okonkwo,+2348033334444,,lapsed,Health policy lapsed Feb 2026\n"
    ),
    "fitness": (
        "name,phone,email,tags,notes\n"
        "Tomi Bakare,+2348011112222,tomi@example.com,trial,Free trial Jan; didn't convert\n"
        "Ife Adeoye,08022223333,ife@example.com,past-member,Returning after baby; injury history\n"
        "Daniel Okoro,+2348033334444,daniel@example.com,referral,Wants strength + mobility plan\n"
    ),
    "events": (
        "name,phone,email,tags,notes\n"
        "Ngozi Eze,+2348011112222,ngozi@example.com,wedding-2026,June wedding, ~250 guests\n"
        "Tobi Adekunle,08022223333,,corporate,Annual gala dinner enquiry\n"
        "Bisi Lawal,+2348033334444,bisi@example.com,birthday,40th birthday, intimate\n"
    ),
    "auto": (
        "name,phone,email,tags,notes\n"
        "Yusuf Audu,+2348011112222,yusuf@example.com,test-drive,SUV; trading in 2019 Camry\n"
        "Chioma Iwu,08022223333,chioma@example.com,service,Last service Aug 2025\n"
        "Femi Ojo,+2348033334444,,enquiry,Asked about 2024 imports\n"
    ),
    "cooperatives": (
        "name,phone,email,tags,notes\n"
        "Ada Onwuka,+2348011112222,ada@example.com,prospective,Referred by member 12\n"
        "Bayo Adeyemi,08022223333,bayo@example.com,member,Cycle 3, ₦25k contribution\n"
        "Chika Eze,+2348033334444,,member,Cycle 4, due for payout in May\n"
    ),
    "general": (
        "name,phone,email,tags,notes\n"
        "Sample Customer,+2348011112222,sample@example.com,warm,Past customer\n"
        "Another Lead,08022223333,another@example.com,referral,Came via word of mouth\n"
    ),
}


def _parse_overrides(raw: Optional[str]) -> Optional[dict]:
    """Decode the column_overrides_json form field into a clean dict.
    Returns None if blank or unparseable — the parser then relies on auto-detect."""
    import json
    if not raw or not raw.strip():
        return None
    try:
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            return None
        return {k: v for k, v in decoded.items() if isinstance(k, str) and isinstance(v, str)}
    except Exception:
        return None


def _enforce_byo_enabled(client_doc: dict) -> None:
    """Block uploads/runs for verticals where BYO Leads is disabled.
    Per-client override via `byo_leads_enabled=False` also respected."""
    if client_doc.get("byo_leads_enabled") is False:
        raise HTTPException(403, f"BYO Leads disabled for client '{client_doc.get('name')}'")
    vertical = client_doc.get("vertical")
    if vertical and vertical not in BYO_LEADS_ENABLED_VERTICALS:
        raise HTTPException(
            403,
            f"BYO Leads is not available for vertical '{vertical}'. "
            f"Allowed: {', '.join(sorted(BYO_LEADS_ENABLED_VERTICALS))}",
        )


def _record_import(
    *,
    client_doc: dict,
    filename: str,
    file_bytes: bytes,
    consent_attestation: bool,
    uploader: Optional[str],
    request: Optional[Request],
    stats: dict,
    vertical: str,
    campaign_tag: Optional[str],
) -> str:
    """Persist one row in lead_imports — the audit trail for NDPR + DPA compliance.

    On Mongo failure we log loudly with the file hash + uploader + counts so
    the audit can be reconstructed out-of-band. We never silently lose
    consent attestation.
    """
    ip = (request.client.host if request and request.client else None)
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    doc = {
        "client_id": client_doc["_id"],
        "client_name": client_doc.get("name"),
        "vertical": vertical,
        "filename": filename,
        "file_hash": file_hash,
        "file_size_bytes": len(file_bytes),
        "campaign_tag": campaign_tag,
        "consent_attestation": bool(consent_attestation),
        "uploader": uploader or "admin",
        "uploader_ip": ip,
        "stats": stats,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        res = get_db()["lead_imports"].insert_one(doc)
        return str(res.inserted_id)
    except Exception as exc:
        log.error(
            "lead_import_audit_write_failed",
            client=client_doc.get("name"),
            filename=filename,
            file_hash=file_hash,
            file_size=len(file_bytes),
            attestation=bool(consent_attestation),
            uploader=uploader,
            ip=ip,
            stats=stats,
            error=str(exc),
        )
        return ""


def _ensure_lead_imports_indexes() -> None:
    from pymongo import ASCENDING, DESCENDING
    col = get_db()["lead_imports"]
    col.create_index([("client_id", ASCENDING), ("created_at", DESCENDING)])
    col.create_index([("file_hash", ASCENDING)])


# ─── Request schemas ──────────────────────────────────────────────────────────

class RunB2CRequest(BaseModel):
    vertical: str = Field(..., description="real_estate | recruitment | events | retail | etc.")
    max_contacts: int = Field(default=50, ge=1, le=200)
    dry_run: bool = Field(default=True)
    hitl_mode: bool = Field(default=False, description="Queue for approval instead of sending directly")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload/{client_name}")
async def upload_b2c_csv(
    client_name: str,
    request: Request,
    file: UploadFile = File(...),
    vertical: Optional[str] = Form(default=None),
    campaign_tag: Optional[str] = Form(default=None),
    consent_attestation: bool = Form(default=False),
    uploader: Optional[str] = Form(default=None),
):
    """Upload a CSV of contacts for a client.

    consent_attestation MUST be true — the uploader is asserting that every
    contact in the file has a lawful basis under NDPR (existing relationship,
    opt-in, or legitimate interest). This attestation is stored in the
    lead_imports audit collection and is the legal shield ReachNG relies on
    when processing the data.
    """
    if not consent_attestation:
        raise HTTPException(
            422,
            "Consent attestation required. Confirm every contact has a lawful basis "
            "under NDPR (existing relationship, opt-in, or legitimate interest) before uploading.",
        )

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV too large. Max {_MAX_CSV_BYTES // 1024}KB.")
    if not content:
        raise HTTPException(400, "Empty file")

    # Resolve client + enforce gating BEFORE parsing — fail fast.
    client_doc = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}, "active": True}
    )
    if not client_doc:
        raise HTTPException(404, f"Client '{client_name}' not found or inactive")
    _enforce_byo_enabled(client_doc)

    effective_vertical = vertical or client_doc.get("vertical") or "general"

    try:
        stats = parse_and_import_csv(
            csv_bytes=content,
            client_name=client_name,
            vertical=effective_vertical,
            campaign_tag=campaign_tag,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    import_id = _record_import(
        client_doc=client_doc,
        filename=file.filename,
        file_bytes=content,
        consent_attestation=consent_attestation,
        uploader=uploader,
        request=request,
        stats=stats,
        vertical=effective_vertical,
        campaign_tag=campaign_tag,
    )

    return {
        "success": True,
        "client": client_name,
        "vertical": effective_vertical,
        "import_id": import_id,
        **stats,
    }


@router.post("/resume/{client_name}")
async def resume_client_outreach(client_name: str):
    """Admin override — flip outreach_paused back off after a manual review.
    Use after the brief has been improved or a noisy list has been pruned."""
    from tools.account_guard import resume_outreach
    if not resume_outreach(client_name=client_name):
        raise HTTPException(404, f"Client '{client_name}' not found")
    return {"success": True, "client": client_name, "outreach_paused": False}


@router.get("/account/{client_name}")
async def get_client_account_status(client_name: str):
    """Snapshot for admin: paused flag + daily cap usage."""
    from tools.account_guard import get_account_status
    return get_account_status(client_name=client_name)


@router.get("/imports/{client_name}")
async def list_imports(client_name: str, limit: int = 50):
    """Audit log: every CSV import for this client + consent attestation timestamp/uploader."""
    client = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{client_name}' not found")
    rows = list(
        get_db()["lead_imports"]
        .find({"client_id": client["_id"]})
        .sort("created_at", -1)
        .limit(min(limit, 200))
    )
    for r in rows:
        r["id"] = str(r.pop("_id"))
        r["client_id"] = str(r["client_id"])
        if hasattr(r.get("created_at"), "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


@router.post("/run/{client_name}")
async def run_b2c_campaign(
    client_name: str,
    body: RunB2CRequest,
    background_tasks: BackgroundTasks,
):
    """
    Run a B2C campaign against contacts uploaded for this client.
    Pulls client brief + Unipile account IDs from the clients collection.

    Hard-gated by:
      - byo_leads_enabled flag + vertical allow-list
      - BusinessBrief health (queue_draft raises BriefIncompleteError if blocked)
    """
    client_doc = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}, "active": True}
    )
    if not client_doc:
        raise HTTPException(404, f"Client '{client_name}' not found or inactive")
    _enforce_byo_enabled(client_doc)

    # Pre-check brief health — fail fast with a useful message rather than letting
    # individual queue_draft calls raise mid-campaign.
    try:
        from services.brief import brief_health
        health = brief_health(client_id=str(client_doc["_id"]))
        if health.get("blockers"):
            raise HTTPException(
                422,
                f"BusinessBrief incomplete for '{client_name}'. Missing: "
                f"{', '.join(health['blockers'])}. Health {health.get('score')}/{health.get('max')}. "
                f"Open the Briefs tab and complete the brief before launching outreach.",
            )
    except HTTPException:
        raise
    except Exception:
        log.exception("brief_health_check_failed", client=client_name)
        raise HTTPException(500, "Brief health check failed — refusing to run campaign.")

    # Pre-check legal pack — same hard gate as brief.
    try:
        from api.legal import is_legal_pack_complete
        if not is_legal_pack_complete(client_name=client_name):
            raise HTTPException(
                422,
                f"Legal pack not signed for '{client_name}'. MSA, DPA, NDA "
                "(and Closer Addendum if applicable) must be accepted before outreach. "
                "Open the Onboarding panel to record acceptance.",
            )
    except HTTPException:
        raise
    except Exception:
        log.exception("legal_pack_check_failed", client=client_name)
        raise HTTPException(500, "Legal pack check failed — refusing to run campaign.")

    campaign = B2CCampaign()

    kwargs = dict(
        client_name=client_name,
        vertical=body.vertical,
        max_contacts=body.max_contacts,
        dry_run=body.dry_run,
        hitl_mode=body.hitl_mode,
        client_brief=client_doc.get("brief"),
        whatsapp_account_id=client_doc.get("whatsapp_account_id"),
        email_account_id=client_doc.get("email_account_id"),
    )

    # Large batches go to background
    if body.max_contacts > 20 and not body.dry_run:
        background_tasks.add_task(campaign.run, **kwargs)
        return {"status": "started", "client": client_name, "message": "B2C campaign running in background"}

    try:
        result = await campaign.run(**kwargs)
    except Exception as exc:
        from tools.hitl import BriefIncompleteError
        from tools.account_guard import OutreachCapExceeded, OutreachPaused
        if isinstance(exc, BriefIncompleteError):
            raise HTTPException(422, str(exc))
        if isinstance(exc, OutreachPaused):
            raise HTTPException(423, str(exc))
        if isinstance(exc, OutreachCapExceeded):
            raise HTTPException(429, str(exc))
        raise
    return result


@router.get("/contacts/{client_name}")
async def list_b2c_contacts(
    client_name: str,
    vertical: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
):
    """List B2C contacts for a client."""
    query: dict = {"client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    if vertical:
        query["vertical"] = vertical
    if status:
        query["status"] = status

    col = get_db()["b2c_contacts"]
    contacts = list(col.find(query).sort("created_at", -1).skip(skip).limit(limit))
    for c in contacts:
        c["id"] = str(c.pop("_id"))
        for f in ("created_at", "updated_at", "last_contacted_at", "opted_out_at"):
            if hasattr(c.get(f), "isoformat"):
                c[f] = c[f].isoformat()
    return contacts


@router.get("/stats/{client_name}")
async def b2c_stats(client_name: str, vertical: Optional[str] = None):
    """Pipeline stats — how many contacts in each status."""
    col = get_db()["b2c_contacts"]
    query: dict = {"client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    if vertical:
        query["vertical"] = vertical

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = list(col.aggregate(pipeline))
    stats = {r["_id"]: r["count"] for r in rows}
    stats["total"] = sum(stats.values())
    return {"client": client_name, "vertical": vertical, "stats": stats}


@router.patch("/contacts/{contact_id}/opted-out")
async def b2c_opt_out(contact_id: str):
    """Mark a B2C contact as opted out. They will never be contacted again."""
    try:
        ObjectId(contact_id)
    except Exception:
        raise HTTPException(400, "Invalid contact ID")

    col = get_db()["b2c_contacts"]
    if not col.find_one({"_id": ObjectId(contact_id)}, {"_id": 1}):
        raise HTTPException(404, "Contact not found")

    mark_b2c_opted_out(contact_id)
    return {"success": True, "status": "opted_out"}


# ─── Portal (token-gated) ─────────────────────────────────────────────────────
# Clients upload + run their own lists from the portal — no Basic Auth.
public_router = APIRouter(prefix="/portal-leads", tags=["BYO Leads — Portal"])


def _client_by_token(token: str, *, enforce_byo: bool = True) -> dict:
    """Resolve a portal token to a client doc.

    Pass enforce_byo=False on read-only routes (status) so the UI can render
    the 'BYO disabled for this vertical' state instead of 403ing.
    """
    client = get_db()["clients"].find_one({"portal_token": token, "active": True})
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    if enforce_byo:
        _enforce_byo_enabled(client)
    return client


@public_router.get("/{token}/status")
async def portal_leads_status(token: str):
    """Health snapshot for the Lead Lists tab — gates + counts + brief readiness.

    Read-only — does NOT 403 when BYO Leads is disabled, so the UI can render
    a clear 'BYO Leads not available for your vertical' state.
    """
    client = _client_by_token(token, enforce_byo=False)
    cid = str(client["_id"])
    name = client.get("name")
    vertical = client.get("vertical")
    byo_disabled_reason: Optional[str] = None
    if client.get("byo_leads_enabled") is False:
        byo_disabled_reason = "Disabled for this client. Contact your account manager."
    elif vertical and vertical not in BYO_LEADS_ENABLED_VERTICALS:
        byo_disabled_reason = f"Not available for vertical '{vertical}'."

    col = get_db()["b2c_contacts"]
    pipeline = [
        {"$match": {"client_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    by_status = {r["_id"]: r["count"] for r in col.aggregate(pipeline)}

    try:
        from services.brief import brief_health
        health = brief_health(client_id=cid)
    except Exception:
        health = {"score": 0, "blockers": ["icp", "closing_action"]}

    try:
        from tools.account_guard import get_account_status
        guard = get_account_status(client_name=name)
    except Exception:
        guard = {}

    byo_enabled = (
        client.get("byo_leads_enabled", True) is not False
        and (not vertical or vertical in BYO_LEADS_ENABLED_VERTICALS)
    )

    return {
        "client": name,
        "vertical": vertical,
        "byo_leads_enabled": byo_enabled,
        "byo_disabled_reason": byo_disabled_reason,
        "contacts_by_status": by_status,
        "total_contacts": sum(by_status.values()),
        "brief_health": health,
        "account_guard": guard,
        "ready_to_run": (
            byo_enabled
            and not (health.get("blockers") or [])
            and not guard.get("outreach_paused")
            and (guard.get("remaining_today", 1) > 0)
        ),
    }


@public_router.post("/{token}/preview")
async def portal_leads_preview(
    token: str,
    file: UploadFile = File(...),
    column_overrides_json: Optional[str] = Form(default=None),
):
    """Pre-import preview — shows the user what would happen without committing.

    Optional column_overrides_json lets the user pin specific CSV headers to
    specific fields when auto-detect misses (e.g. {"phone": "GSM"}).
    No DB writes happen here.
    """
    client = _client_by_token(token)
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV too large. Max {_MAX_CSV_BYTES // 1024}KB.")
    if not content:
        raise HTTPException(400, "Empty file")
    overrides = _parse_overrides(column_overrides_json)
    return preview_csv(content, client_name=client.get("name"), column_overrides=overrides)


@public_router.post("/{token}/upload")
async def portal_leads_upload(
    token: str,
    request: Request,
    file: UploadFile = File(...),
    campaign_tag: Optional[str] = Form(default=None),
    consent_attestation: bool = Form(default=False),
    column_overrides_json: Optional[str] = Form(default=None),
):
    """Client-side CSV upload from the portal. Same compliance rails as admin.

    `column_overrides_json` is the user's pinned column mapping from the
    preview UI — applied on top of the parser's auto-detect.
    """
    client = _client_by_token(token)

    if not consent_attestation:
        raise HTTPException(
            422,
            "Tick the consent attestation box. You must confirm every contact has a "
            "lawful basis under NDPR before we can process the file.",
        )
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV too large. Max {_MAX_CSV_BYTES // 1024}KB.")
    if not content:
        raise HTTPException(400, "Empty file")

    vertical = client.get("vertical") or "general"
    overrides = _parse_overrides(column_overrides_json)
    try:
        stats = parse_and_import_csv(
            csv_bytes=content,
            client_name=client.get("name"),
            vertical=vertical,
            campaign_tag=campaign_tag,
            column_overrides=overrides,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    import_id = _record_import(
        client_doc=client,
        filename=file.filename,
        file_bytes=content,
        consent_attestation=consent_attestation,
        uploader=f"portal:{token[:8]}",
        request=request,
        stats=stats,
        vertical=vertical,
        campaign_tag=campaign_tag,
    )

    return {"success": True, "client": client.get("name"), "vertical": vertical, "import_id": import_id, **stats}


@public_router.post("/{token}/run")
async def portal_leads_run(token: str, body: RunB2CRequest, background_tasks: BackgroundTasks):
    """Client-side campaign launch from the portal. Hard-gated by brief health."""
    client = _client_by_token(token)

    try:
        from services.brief import brief_health
        health = brief_health(client_id=str(client["_id"]))
        if health.get("blockers"):
            raise HTTPException(
                422,
                "Outreach paused — Business Brief incomplete. Missing: "
                f"{', '.join(health['blockers'])}. Open the Business Brief tab and finish "
                "the brief before launching a campaign.",
            )
    except HTTPException:
        raise
    except Exception:
        log.exception("portal_brief_health_failed", token_prefix=token[:8])
        raise HTTPException(500, "Brief health check failed — refusing to run campaign.")

    try:
        from api.legal import is_legal_pack_complete
        if not is_legal_pack_complete(client_id=str(client["_id"])):
            raise HTTPException(
                422,
                "Outreach paused — legal pack not yet accepted. Please review and accept "
                "MSA, DPA, NDA (and Closer Addendum where applicable) on the Onboarding tab.",
            )
    except HTTPException:
        raise
    except Exception:
        log.exception("portal_legal_check_failed", token_prefix=token[:8])
        raise HTTPException(500, "Legal pack check failed — refusing to run campaign.")

    campaign = B2CCampaign()
    kwargs = dict(
        client_name=client.get("name"),
        vertical=body.vertical or client.get("vertical") or "general",
        max_contacts=body.max_contacts,
        dry_run=body.dry_run,
        hitl_mode=True,  # portal launches always go through approval queue
        client_brief=client.get("brief"),
        whatsapp_account_id=client.get("whatsapp_account_id"),
        email_account_id=client.get("email_account_id"),
    )

    if body.max_contacts > 20 and not body.dry_run:
        background_tasks.add_task(campaign.run, **kwargs)
        return {"status": "started", "client": client.get("name"), "message": "Campaign running in background"}

    try:
        return await campaign.run(**kwargs)
    except Exception as exc:
        from tools.hitl import BriefIncompleteError
        from tools.account_guard import OutreachCapExceeded, OutreachPaused
        if isinstance(exc, BriefIncompleteError):
            raise HTTPException(422, str(exc))
        if isinstance(exc, OutreachPaused):
            raise HTTPException(423, str(exc))
        if isinstance(exc, OutreachCapExceeded):
            raise HTTPException(429, str(exc))
        raise


@public_router.get("/{token}/imports")
async def portal_leads_imports(token: str, limit: int = 30):
    """Client sees their own import history."""
    client = _client_by_token(token)
    rows = list(
        get_db()["lead_imports"]
        .find({"client_id": client["_id"]})
        .sort("created_at", -1)
        .limit(min(limit, 100))
    )
    for r in rows:
        r["id"] = str(r.pop("_id"))
        r["client_id"] = str(r["client_id"])
        if hasattr(r.get("created_at"), "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


@public_router.get("/{token}/suppression")
async def portal_leads_suppression(token: str):
    """Suppression-list summary for the portal.

    Returns counts only — never names/phones — to satisfy NDPR. The owner sees
    'X contacts have opted out and will never be messaged again' rather than
    a list of personal data.
    """
    client = _client_by_token(token, enforce_byo=False)
    name = client.get("name")
    col = get_db()["b2c_contacts"]
    query = {"client_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    opted_out = col.count_documents({**query, "status": "opted_out"})
    total     = col.count_documents(query)
    return {
        "client": name,
        "opted_out": opted_out,
        "total_contacts": total,
        "opt_out_rate_pct": round((opted_out / total) * 100, 2) if total else 0.0,
    }


class TestSendPayload(BaseModel):
    phone: str = Field(..., description="Owner's own number to receive the test draft")
    sample_name: str = Field(default="Test Customer")
    sample_notes: Optional[str] = None


@public_router.post("/{token}/test-send")
async def portal_leads_test_send(token: str, payload: TestSendPayload):
    """Generate a draft using the BusinessBrief and queue it to ONE phone the
    owner controls — for sanity-checking voice/tone before launching a campaign.

    Routes through queue_draft like everything else, so the brief gate + caps
    apply. The owner approves it from the dashboard like a normal draft.
    """
    client = _client_by_token(token)
    client_name = client.get("name")
    vertical = client.get("vertical") or "general"

    from agent.brain import generate_b2c_message
    from tools.hitl import queue_draft, BriefIncompleteError
    from tools.account_guard import OutreachCapExceeded, OutreachPaused

    try:
        generated = generate_b2c_message(
            customer_name=payload.sample_name,
            channel="whatsapp",
            vertical=vertical,
            client_name=client_name,
            notes=payload.sample_notes,
            tags=["test-send"],
        )
    except Exception as e:
        raise HTTPException(500, f"Draft generation failed: {e}")

    # Synthetic contact_id — test-send drafts aren't tied to a real contact row.
    synthetic_id = ObjectId()
    try:
        approval_id = queue_draft(
            contact_id=str(synthetic_id),
            contact_name=payload.sample_name,
            vertical=vertical,
            channel="whatsapp",
            message=generated.get("message", ""),
            phone=payload.phone,
            source="byo_leads",
            client_name=client_name,
        )
    except BriefIncompleteError as e:
        raise HTTPException(422, str(e))
    except OutreachPaused as e:
        raise HTTPException(423, str(e))
    except OutreachCapExceeded as e:
        raise HTTPException(429, str(e))

    return {
        "success": True,
        "approval_id": approval_id,
        "preview": generated.get("message", ""),
        "message": "Draft queued. Approve it from the Message Queue to deliver to the test phone.",
    }


@public_router.get("/{token}/sample.csv")
async def portal_leads_sample_csv(token: str):
    """Vertical-tuned sample CSV — gives clients a working template instead of
    asking them to guess column names. Headers match what the parser auto-detects.
    """
    from fastapi.responses import PlainTextResponse
    client = _client_by_token(token, enforce_byo=False)
    vertical = client.get("vertical") or "general"
    csv_text = _SAMPLE_CSV_BY_VERTICAL.get(vertical, _SAMPLE_CSV_BY_VERTICAL["general"])
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reachng-sample-{vertical}.csv"'},
    )


@public_router.get("/{token}/contacts")
async def portal_leads_contacts(token: str, status: Optional[str] = None, limit: int = 100, skip: int = 0):
    """Contacts list scoped to this client only — never cross-client."""
    client = _client_by_token(token)
    name = client.get("name")
    query: dict = {"client_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if status:
        query["status"] = status

    col = get_db()["b2c_contacts"]
    contacts = list(col.find(query).sort("created_at", -1).skip(skip).limit(min(limit, 500)))
    for c in contacts:
        c["id"] = str(c.pop("_id"))
        for f in ("created_at", "updated_at", "last_contacted_at", "opted_out_at"):
            if hasattr(c.get(f), "isoformat"):
                c[f] = c[f].isoformat()
    return contacts
