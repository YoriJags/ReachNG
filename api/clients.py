"""
Client management — each paying ReachNG client gets their own campaign brief.
The brief replaces the generic vertical prompt, making every message on-brand for them.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db

router = APIRouter(prefix="/clients", tags=["Clients"])


def get_clients():
    return get_db()["clients"]


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ClientUpsert(BaseModel):
    name: str                    # e.g. "Mercury Lagos"
    vertical: str                # real_estate | recruitment | events
    brief: str                   # Who they are, what they're selling, tone, target customer
    preferred_channel: str = "whatsapp"
    active: bool = True
    plan: str | None = None      # starter | growth | agency


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_clients():
    clients = list(get_clients().find({}).sort("created_at", -1))
    return [_serialise(c) for c in clients]


@router.get("/{name}")
async def get_client(name: str):
    client = get_clients().find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")
    return _serialise(client)


@router.post("/")
async def upsert_client(payload: ClientUpsert):
    """Create or update a client brief."""
    now = datetime.now(timezone.utc)
    clients = get_clients()

    result = clients.update_one(
        {"name": {"$regex": f"^{payload.name}$", "$options": "i"}},
        {
            "$set": {
                "name": payload.name,
                "vertical": payload.vertical,
                "brief": payload.brief,
                "preferred_channel": payload.preferred_channel,
                "active": payload.active,
                "plan": payload.plan,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    action = "created" if result.upserted_id else "updated"
    return {"success": True, "action": action, "client": payload.name}


@router.delete("/{name}")
async def deactivate_client(name: str):
    """Soft-delete — marks client inactive without removing their brief."""
    result = get_clients().update_one(
        {"name": {"$regex": f"^{name}$", "$options": "i"}},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "status": "deactivated"}
