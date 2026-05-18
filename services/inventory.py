"""
Structured availability inventory per client.

Each row is a sellable item with a real-time availability status the owner
maintains. EYO reads these at draft time (via agent/brain.py's
_availability_safety_block) and CITES them when a customer asks "is X
available?"

If an item isn't listed OR no inventory exists at all, EYO falls back to
the BusinessBrief.availability_notes free-text blob; if that's also empty,
the universal safety rail kicks in ("let me check and revert").

Owner-facing CRUD. Scope-locked by client_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from pydantic import BaseModel, Field

from database import get_db

log = structlog.get_logger()


# ─── Model ────────────────────────────────────────────────────────────────

# status vocabulary kept small and self-explanatory in drafts
ALLOWED_STATUS = {"available", "limited", "unavailable"}


class InventoryItem(BaseModel):
    name:        str  = Field(..., min_length=1, max_length=120)
    category:    str  = Field("",  max_length=60)         # e.g. "Table", "Property", "Slot"
    status:      str  = Field("available")                # available | limited | unavailable
    notes:       str  = Field("",  max_length=300)        # human nuance EYO can quote
    valid_until: Optional[datetime] = None                 # auto-expire status after this date


def _coerce_status(s: str) -> str:
    s = (s or "").lower().strip()
    return s if s in ALLOWED_STATUS else "available"


# ─── Collections + indexes ─────────────────────────────────────────────────

def _col():
    return get_db()["client_inventory"]


def ensure_inventory_indexes() -> None:
    col = _col()
    col.create_index([("client_id", 1)])
    col.create_index([("client_id", 1), ("name", 1)])
    col.create_index([("valid_until", 1)], sparse=True)


# ─── CRUD ─────────────────────────────────────────────────────────────────

def list_items(client_id: str) -> list[dict]:
    """Return all inventory items for the client, sorted by category + name."""
    if not client_id:
        return []
    rows = list(_col().find({"client_id": client_id}).sort([("category", 1), ("name", 1)]))
    for r in rows:
        r["_id"] = str(r["_id"])
        for k in ("created_at", "updated_at", "valid_until"):
            if r.get(k) and isinstance(r[k], datetime):
                r[k] = r[k].isoformat()
    return rows


def upsert_item(client_id: str, *, item_id: Optional[str], item: InventoryItem) -> str:
    """Insert or update. Returns the item _id as string."""
    if not client_id:
        raise ValueError("client_id required")

    now = datetime.now(timezone.utc)
    doc = {
        "client_id":   client_id,
        "name":        item.name.strip()[:120],
        "category":    (item.category or "").strip()[:60],
        "status":      _coerce_status(item.status),
        "notes":       (item.notes or "").strip()[:300],
        "valid_until": item.valid_until,
        "updated_at":  now,
    }

    if item_id:
        try:
            oid = ObjectId(item_id)
        except Exception:
            raise ValueError("invalid item_id")
        _col().update_one(
            {"_id": oid, "client_id": client_id},
            {"$set": doc},
        )
        return item_id

    doc["created_at"] = now
    res = _col().insert_one(doc)
    return str(res.inserted_id)


def delete_item(client_id: str, item_id: str) -> bool:
    try:
        oid = ObjectId(item_id)
    except Exception:
        return False
    res = _col().delete_one({"_id": oid, "client_id": client_id})
    return res.deleted_count > 0


def count_items(client_id: str) -> dict:
    """Aggregate counts by status for the dashboard badge."""
    if not client_id:
        return {"total": 0, "available": 0, "limited": 0, "unavailable": 0}
    pipeline = [
        {"$match": {"client_id": client_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    out = {"available": 0, "limited": 0, "unavailable": 0}
    total = 0
    for row in _col().aggregate(pipeline):
        s = row.get("_id") or "available"
        if s in out:
            out[s] = row["n"]
        total += row["n"]
    out["total"] = total
    return out
