from fastapi import APIRouter, HTTPException
from bson import ObjectId
from database import get_contacts
from tools import mark_replied, mark_converted, mark_opted_out, get_pipeline_stats
from tools.memory import Status

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


@router.get("/pipeline")
async def pipeline_summary():
    """Counts per status across all verticals — dashboard view."""
    summary = {}
    for vertical in ["real_estate", "recruitment", "events"]:
        summary[vertical] = get_pipeline_stats(vertical=vertical)
    summary["all"] = get_pipeline_stats()
    return summary


@router.patch("/{contact_id}/replied")
async def contact_replied(contact_id: str):
    _validate_id(contact_id)
    mark_replied(contact_id)
    return {"success": True, "status": Status.REPLIED}


@router.patch("/{contact_id}/converted")
async def contact_converted(contact_id: str):
    _validate_id(contact_id)
    mark_converted(contact_id)
    return {"success": True, "status": Status.CONVERTED}


@router.patch("/{contact_id}/opted-out")
async def contact_opted_out(contact_id: str):
    _validate_id(contact_id)
    mark_opted_out(contact_id)
    return {"success": True, "status": Status.OPTED_OUT}


def _validate_id(contact_id: str):
    try:
        ObjectId(contact_id)
    except Exception:
        raise HTTPException(400, "Invalid contact ID")
