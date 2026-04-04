import csv
import io
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
from database import get_contacts, get_replies
from tools import mark_replied, mark_converted, mark_opted_out, get_pipeline_stats
from tools.memory import Status
from tools.reply_router import process_replies

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if "contact_id" in doc:
        doc["contact_id"] = str(doc["contact_id"])
    return doc


@router.get("/")
async def list_contacts(
    vertical: str | None = None,
    status: str | None = None,
    limit: int = 50,
    skip: int = 0,
):
    query = {}
    if vertical:
        query["vertical"] = vertical
    if status:
        query["status"] = status

    contacts = list(
        get_contacts()
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [_serialise(c) for c in contacts]


@router.get("/export")
async def export_contacts(
    vertical: str | None = None,
    status: str | None = None,
    fmt: str = Query(default="csv", pattern="^csv$"),
):
    """Export contacts as a CSV download. Importable directly into Google Sheets."""
    query = {}
    if vertical:
        query["vertical"] = vertical
    if status:
        query["status"] = status

    contacts = list(get_contacts().find(query).sort("created_at", -1))

    fields = ["name", "vertical", "status", "phone", "email", "website",
              "address", "category", "rating", "outreach_count",
              "last_contacted_at", "created_at"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for c in contacts:
        row = {f: c.get(f, "") for f in fields}
        # Flatten datetime objects
        for dt_field in ("last_contacted_at", "created_at"):
            val = row.get(dt_field)
            if hasattr(val, "isoformat"):
                row[dt_field] = val.isoformat()
        writer.writerow(row)

    buf.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"reachng_contacts_{timestamp}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pipeline")
async def pipeline_summary():
    """Counts per status across all verticals — dashboard view."""
    summary = {}
    for vertical in ["real_estate", "recruitment", "events", "fintech", "legal", "logistics", "agriculture"]:
        raw = get_pipeline_stats(vertical=vertical)
        summary[vertical] = {
            "contacted":     raw.get("contacted", 0),
            "replied":       raw.get("replied", 0),
            "converted":     raw.get("converted", 0),
            "opted_out":     raw.get("opted_out", 0),
            "not_contacted": raw.get("new", 0),
            "daily_sent":    raw.get("daily_sent", 0),
        }
    all_raw = get_pipeline_stats()
    summary["all"] = {
        "contacted":  all_raw.get("contacted", 0),
        "replied":    all_raw.get("replied", 0),
        "converted":  all_raw.get("converted", 0),
        "opted_out":  all_raw.get("opted_out", 0),
        "daily_sent": all_raw.get("daily_sent", 0),
    }
    return summary


@router.patch("/{contact_id}/replied")
async def contact_replied(contact_id: str):
    _validate_id(contact_id)
    _require_contact(contact_id)
    mark_replied(contact_id)
    return {"success": True, "status": Status.REPLIED}


@router.patch("/{contact_id}/converted")
async def contact_converted(contact_id: str):
    _validate_id(contact_id)
    _require_contact(contact_id)
    mark_converted(contact_id)
    return {"success": True, "status": Status.CONVERTED}


@router.patch("/{contact_id}/opted-out")
async def contact_opted_out(contact_id: str):
    _validate_id(contact_id)
    _require_contact(contact_id)
    mark_opted_out(contact_id)
    return {"success": True, "status": Status.OPTED_OUT}


@router.get("/replies")
async def list_replies(limit: int = 50, channel: str | None = None):
    """Recent inbound replies — matched and unmatched."""
    query = {}
    if channel:
        query["channel"] = channel

    replies = list(
        get_replies()
        .find(query)
        .sort("received_at", -1)
        .limit(limit)
    )
    return [_serialise(r) for r in replies]


@router.post("/replies/sync")
async def sync_replies(background_tasks: BackgroundTasks):
    """Manually trigger a reply poll — don't wait for the scheduler."""
    background_tasks.add_task(process_replies)
    return {"message": "Reply sync started"}


def _validate_id(contact_id: str):
    try:
        ObjectId(contact_id)
    except Exception:
        raise HTTPException(400, "Invalid contact ID")


def _require_contact(contact_id: str):
    if not get_contacts().find_one({"_id": ObjectId(contact_id)}, {"_id": 1}):
        raise HTTPException(404, "Contact not found")
