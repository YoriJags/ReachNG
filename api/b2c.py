"""
B2C API — CSV upload + campaign trigger for consumer outreach.

Endpoints:
  POST /b2c/upload/{client_name}         — Upload CSV, import contacts
  POST /b2c/run/{client_name}            — Run campaign against imported contacts
  GET  /b2c/contacts/{client_name}       — List B2C contacts for a client
  GET  /b2c/stats/{client_name}          — Pipeline stats for B2C contacts
  PATCH /b2c/contacts/{id}/opted-out     — Manual opt-out (GDPR compliance)
"""
import re
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from database import get_db
from tools.csv_import import (
    parse_and_import_csv, get_b2c_contacts_for_campaign,
    mark_b2c_opted_out, ensure_b2c_indexes,
)
from campaigns.b2c import B2CCampaign
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/b2c", tags=["B2C"])

_MAX_CSV_BYTES = 5 * 1024 * 1024   # 5 MB — enough for 100k rows


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
    file: UploadFile = File(...),
    vertical: str = "general",
    campaign_tag: Optional[str] = None,
):
    """
    Upload a CSV of customer contacts for a client.
    Columns auto-detected. Required: phone or whatsapp column.
    Optional: name, email, notes, tags.

    Example curl:
        curl -X POST /api/v1/b2c/upload/MercuryLagos \\
          -F "file=@customers.csv" \\
          -F "vertical=real_estate"
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV too large. Max {_MAX_CSV_BYTES // 1024}KB.")
    if not content:
        raise HTTPException(400, "Empty file")

    try:
        stats = parse_and_import_csv(
            csv_bytes=content,
            client_name=client_name,
            vertical=vertical,
            campaign_tag=campaign_tag,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return {
        "success": True,
        "client": client_name,
        "vertical": vertical,
        **stats,
    }


@router.post("/run/{client_name}")
async def run_b2c_campaign(
    client_name: str,
    body: RunB2CRequest,
    background_tasks: BackgroundTasks,
):
    """
    Run a B2C campaign against contacts uploaded for this client.
    Pulls client brief + Unipile account IDs from the clients collection.
    """
    # Load client config
    client_doc = get_db()["clients"].find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}, "active": True}
    )
    if not client_doc:
        raise HTTPException(404, f"Client '{client_name}' not found or inactive")

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

    result = await campaign.run(**kwargs)
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
