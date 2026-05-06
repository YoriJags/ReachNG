"""
Venue capacity management — tracks available space per date for hospitality clients.

The AI Closer reads capacity before drafting replies so it never promises
availability on a full night or fails to upsell on a quiet one.
"""
from datetime import datetime, date, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from bson import ObjectId
from database import get_db
from auth import require_auth
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/venue", tags=["Venue Capacity"])


def get_capacity_col():
    return get_db()["venue_capacity"]


def ensure_capacity_indexes():
    col = get_capacity_col()
    from pymongo import ASCENDING
    col.create_index([("client_name", ASCENDING), ("date", ASCENDING)], unique=True)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CapacityUpsert(BaseModel):
    client_name: str
    date: str = Field(..., description="ISO date string e.g. 2026-05-10")
    total_capacity: int = Field(default=150, description="Max pax the venue holds")
    confirmed_bookings_pax: int = Field(default=0, description="Pax already confirmed via bookings")
    is_private_event: bool = Field(default=False, description="Venue fully closed for private hire")
    is_closed: bool = Field(default=False, description="Venue closed this day")
    note: Optional[str] = Field(default=None, description="Staff note e.g. 'Birthday takeover'")


class CapacityBulk(BaseModel):
    client_name: str
    days: list[CapacityUpsert]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _capacity_signal(doc: dict) -> str:
    """
    Returns a natural-language availability signal the AI can inject into prompts.
    e.g. "Saturday 10 May: venue is at full capacity — private event. Suggest Sunday."
    """
    d = doc.get("date", "")
    if doc.get("is_closed"):
        return f"{d}: venue is closed."
    if doc.get("is_private_event"):
        note = doc.get("note", "private event")
        return f"{d}: fully closed for {note}. Alternative nights available."

    total = doc.get("total_capacity", 150)
    booked = doc.get("confirmed_bookings_pax", 0)
    remaining = max(0, total - booked)
    pct = booked / total if total else 0

    if pct >= 0.95:
        return f"{d}: nearly full ({remaining} pax remaining). Recommend confirming immediately or suggest an alternative."
    if pct >= 0.70:
        return f"{d}: filling up — {remaining} pax of capacity remaining. Good availability for small groups."
    if pct >= 0.30:
        return f"{d}: moderate capacity — {remaining} pax available. Walk-ins and reservations both welcome."
    return f"{d}: plenty of space available. Great night to come through."


def get_capacity_context(client_name: str, target_date: Optional[str] = None) -> str:
    """
    Called by the AI Closer before drafting a reply.
    Returns a 1-3 sentence availability context string.
    If target_date is None, returns the next 7 days summary.
    """
    col = get_capacity_col()

    if target_date:
        doc = col.find_one({"client_name": client_name, "date": target_date})
        if doc:
            return _capacity_signal(doc)
        return f"{target_date}: no capacity data — assume normal availability."

    # Next 7 days summary
    today = date.today()
    signals = []
    for i in range(7):
        d = (today + timedelta(days=i)).isoformat()
        doc = col.find_one({"client_name": client_name, "date": d})
        if doc:
            signals.append(_capacity_signal(doc))
    if not signals:
        return "No capacity data configured — assume normal availability all week."
    return " | ".join(signals)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{client_name}/capacity")
async def get_capacity(client_name: str, weeks: int = 2):
    """Get capacity grid for a client — next N weeks."""
    col = get_capacity_col()
    today = date.today()
    end = today + timedelta(weeks=weeks)
    docs = list(col.find(
        {"client_name": client_name, "date": {"$gte": today.isoformat(), "$lte": end.isoformat()}},
        {"_id": 0}
    ).sort("date", 1))
    return docs


@router.post("/{client_name}/capacity", dependencies=[Depends(require_auth)])
async def upsert_capacity(client_name: str, payload: CapacityUpsert):
    """Set or update capacity for a specific date."""
    col = get_capacity_col()
    payload.client_name = client_name
    doc = payload.model_dump()
    doc["updated_at"] = datetime.now(timezone.utc)
    col.update_one(
        {"client_name": client_name, "date": payload.date},
        {"$set": doc},
        upsert=True,
    )
    log.info("capacity_upsert", client=client_name, date=payload.date)
    return {"status": "ok", "signal": _capacity_signal(doc)}


@router.post("/{client_name}/capacity/bulk", dependencies=[Depends(require_auth)])
async def bulk_upsert_capacity(client_name: str, payload: CapacityBulk):
    """Set capacity for multiple dates at once."""
    col = get_capacity_col()
    now = datetime.now(timezone.utc)
    results = []
    for day in payload.days:
        day.client_name = client_name
        doc = day.model_dump()
        doc["updated_at"] = now
        col.update_one(
            {"client_name": client_name, "date": day.date},
            {"$set": doc},
            upsert=True,
        )
        results.append({"date": day.date, "signal": _capacity_signal(doc)})
    return {"updated": len(results), "days": results}


@router.post("/{client_name}/capacity/{event_date}/book")
async def record_booking(client_name: str, event_date: str, pax: int = 1):
    """
    Increment confirmed_bookings_pax when a booking is confirmed via HITL approval.
    Called automatically by the Closer when a booking draft is approved.
    """
    col = get_capacity_col()
    result = col.update_one(
        {"client_name": client_name, "date": event_date},
        {"$inc": {"confirmed_bookings_pax": pax}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        # Create a stub record if none exists
        col.insert_one({
            "client_name": client_name,
            "date": event_date,
            "total_capacity": 150,
            "confirmed_bookings_pax": pax,
            "is_private_event": False,
            "is_closed": False,
            "updated_at": datetime.now(timezone.utc),
        })
    doc = col.find_one({"client_name": client_name, "date": event_date}, {"_id": 0})
    return {"status": "ok", "signal": _capacity_signal(doc)}
