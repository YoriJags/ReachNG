import csv
import io
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
import httpx
from database import get_contacts, get_replies
from tools import mark_replied, mark_converted, mark_opted_out, get_pipeline_stats
from tools.memory import Status
from tools.reply_router import process_replies
from config import get_settings

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


@router.get("/discovery-health")
async def discovery_health():
    """
    Returns lead source breakdown (maps/apollo/social counts) +
    live API status for each discovery source.
    """
    settings = get_settings()
    db = get_contacts()

    # ── Lead counts by source ──────────────────────────────────────────────────
    pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}}
    ]
    source_counts = {row["_id"]: row["count"] for row in db.aggregate(pipeline) if row["_id"]}
    maps_count   = source_counts.get("maps", 0)
    apollo_count = source_counts.get("apollo", 0)
    social_count = source_counts.get("social", 0)
    unknown_count = sum(v for k, v in source_counts.items() if k not in ("maps", "apollo", "social"))

    # ── Google Maps API ping ───────────────────────────────────────────────────
    maps_status = "unknown"
    maps_error  = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": "business Lagos", "key": settings.google_maps_api_key, "region": "ng"},
            )
            data = resp.json()
            api_status = data.get("status", "")
            if api_status == "OK" or api_status == "ZERO_RESULTS":
                maps_status = "ok"
            elif api_status in ("REQUEST_DENIED", "INVALID_REQUEST"):
                maps_status = "error"
                maps_error  = data.get("error_message") or api_status
            else:
                maps_status = "warn"
                maps_error  = api_status
    except Exception as e:
        maps_status = "error"
        maps_error  = str(e)

    # ── Apollo API ping ────────────────────────────────────────────────────────
    apollo_status = "unknown"
    apollo_error  = None
    apollo_key = getattr(settings, "apollo_api_key", None)
    if not apollo_key:
        apollo_status = "missing"
        apollo_error  = "APOLLO_API_KEY not set"
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    headers={"Content-Type": "application/json", "X-Api-Key": apollo_key},
                    json={"q_organization_name": "test", "page": 1, "per_page": 1},
                )
                if resp.status_code == 200:
                    apollo_status = "ok"
                elif resp.status_code == 401:
                    apollo_status = "error"
                    apollo_error  = "Invalid API key"
                else:
                    apollo_status = "warn"
                    apollo_error  = f"HTTP {resp.status_code}"
        except Exception as e:
            apollo_status = "error"
            apollo_error  = str(e)

    # ── Social (Apify) ping ────────────────────────────────────────────────────
    social_status = "unknown"
    social_error  = None
    apify_token = getattr(settings, "apify_api_token", None)
    if not apify_token:
        social_status = "missing"
        social_error  = "APIFY_API_TOKEN not set"
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.apify.com/v2/acts/clockworks~tiktok-scraper",
                    params={"token": apify_token},
                )
                social_status = "ok" if resp.status_code == 200 else "warn"
                if resp.status_code != 200:
                    social_error = f"HTTP {resp.status_code}"
        except Exception as e:
            social_status = "error"
            social_error  = str(e)

    return {
        "sources": {
            "maps":   {"count": maps_count,   "status": maps_status,   "error": maps_error},
            "apollo": {"count": apollo_count, "status": apollo_status, "error": apollo_error},
            "social": {"count": social_count, "status": social_status, "error": social_error},
        },
        "unknown_source_count": unknown_count,
        "total": maps_count + apollo_count + social_count + unknown_count,
    }


def _validate_id(contact_id: str):
    try:
        ObjectId(contact_id)
    except Exception:
        raise HTTPException(400, "Invalid contact ID")


def _require_contact(contact_id: str):
    if not get_contacts().find_one({"_id": ObjectId(contact_id)}, {"_id": 1}):
        raise HTTPException(404, "Contact not found")
