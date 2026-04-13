import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
    state: str | None = None,
    source: str | None = None,
    limit: int = 50,
    skip: int = 0,
):
    query = {}
    if vertical:
        query["vertical"] = vertical
    if status:
        query["status"] = status
    if state:
        query["state"] = {"$regex": f"^{state}$", "$options": "i"}
    if source:
        query["source"] = source

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
    state: str | None = None,
    source: str | None = None,
    fmt: str = Query(default="csv", pattern="^csv$"),
):
    """Export contacts as a CSV download. Importable directly into Google Sheets."""
    query = {}
    if vertical:
        query["vertical"] = vertical
    if status:
        query["status"] = status
    if state:
        query["state"] = {"$regex": f"^{state}$", "$options": "i"}
    if source:
        query["source"] = source

    contacts = list(get_contacts().find(query).sort("created_at", -1))

    fields = ["name", "vertical", "status", "state", "source", "phone", "email",
              "website", "address", "category", "rating", "outreach_count",
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
        "hot_leads":  all_raw.get("hot_leads", 0),
        "warm_leads": all_raw.get("warm_leads", 0),
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


class CloseDealBody(BaseModel):
    deal_value_ngn: int = 0
    notes: str = ""


@router.patch("/{contact_id}/closed-won")
async def contact_closed_won(contact_id: str, body: CloseDealBody):
    """Mark a lead as closed/won by the client. Records deal value for ROI tracking."""
    _validate_id(contact_id)
    _require_contact(contact_id)
    now = datetime.now(timezone.utc)
    get_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {
            "closed_by_client": True,
            "closed_at": now,
            "deal_value_ngn": body.deal_value_ngn,
            "closed_notes": body.notes,
            "status": Status.CONVERTED,
        }},
    )
    return {"success": True, "status": "closed_won", "deal_value_ngn": body.deal_value_ngn}


@router.get("/replies")
async def list_replies(limit: int = 50, channel: str | None = None):
    """Recent inbound replies — hot leads (interested) sorted to top, then by recency."""
    query = {}
    if channel:
        query["channel"] = channel

    replies = list(
        get_replies()
        .find(query)
        .sort("received_at", -1)
        .limit(limit)
    )
    if not replies:
        return []

    # Sort in Python: interested first, then by recency
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    replies.sort(key=lambda r: (
        0 if r.get("intent") == "interested" else 1,
        -(r["received_at"].replace(tzinfo=timezone.utc) if r.get("received_at") and r["received_at"].tzinfo is None else r.get("received_at") or epoch).timestamp(),
    ))
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
    signal_count = source_counts.get("signal", 0)
    unknown_count = sum(v for k, v in source_counts.items() if k not in ("maps", "apollo", "social", "signal"))

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

    # Signal Intelligence status — check which tokens are configured
    signal_status = "ok" if any([
        settings.fb_ads_access_token,
        settings.twitter_bearer_token,
        settings.apify_api_token,
        settings.apollo_api_key,
    ]) else "missing"
    signal_platforms = []
    if settings.fb_ads_access_token:  signal_platforms.append("fb_ads")
    if settings.twitter_bearer_token: signal_platforms.append("twitter")
    if settings.apify_api_token:      signal_platforms.append("ig/tiktok")
    if settings.apollo_api_key:       signal_platforms.append("linkedin")

    return {
        "sources": {
            "maps":   {"count": maps_count,   "status": maps_status,   "error": maps_error},
            "apollo": {"count": apollo_count, "status": apollo_status, "error": apollo_error},
            "social": {"count": social_count, "status": social_status, "error": social_error},
            "signal": {"count": signal_count, "status": signal_status, "platforms": signal_platforms},
        },
        "unknown_source_count": unknown_count,
        "total": maps_count + apollo_count + social_count + signal_count + unknown_count,
    }


def _validate_id(contact_id: str):
    try:
        ObjectId(contact_id)
    except Exception:
        raise HTTPException(400, "Invalid contact ID")


def _require_contact(contact_id: str):
    if not get_contacts().find_one({"_id": ObjectId(contact_id)}, {"_id": 1}):
        raise HTTPException(404, "Contact not found")
