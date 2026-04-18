"""
Fleet Dispatcher — MongoDB store for trucks and breakdown incidents.
"""
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db


def get_trucks():
    return get_db()["fleet_trucks"]


def get_incidents():
    return get_db()["fleet_incidents"]


def ensure_indexes():
    get_trucks().create_index("plate", unique=True)
    get_incidents().create_index([("status", 1), ("created_at", -1)])


# ─── Trucks ───────────────────────────────────────────────────────────────────

def upsert_truck(plate: str, driver_name: str, make: str = "", model: str = "",
                 current_km: int = 0, client_name: str = "") -> str:
    now = datetime.now(timezone.utc)
    result = get_trucks().update_one(
        {"plate": plate.upper()},
        {
            "$set": {
                "driver_name": driver_name,
                "make": make, "model": model,
                "current_km": current_km,
                "client_name": client_name,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "incident_count": 0},
        },
        upsert=True,
    )
    if result.upserted_id:
        return str(result.upserted_id)
    truck = get_trucks().find_one({"plate": plate.upper()})
    return str(truck["_id"]) if truck else ""


def get_truck(plate: str) -> dict | None:
    return get_trucks().find_one({"plate": plate.upper()})


def list_trucks() -> list[dict]:
    trucks = list(get_trucks().find({}).sort("created_at", -1))
    for t in trucks:
        t["id"] = str(t.pop("_id"))
        for f in ("created_at", "updated_at"):
            if hasattr(t.get(f), "isoformat"):
                t[f] = t[f].isoformat()
    return trucks


def get_truck_incident_history(plate: str, limit: int = 5) -> list[dict]:
    """Return last N incidents for a truck — context for Claude assessment."""
    incidents = list(
        get_incidents()
        .find({"truck_plate": plate.upper()})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [
        {
            "date": inc.get("created_at", "").isoformat() if hasattr(inc.get("created_at"), "isoformat") else "",
            "issue": inc.get("issue_summary", ""),
            "amount_approved": inc.get("amount_approved_ngn", 0),
            "resolved": inc.get("status") == "resolved",
        }
        for inc in incidents
    ]


# ─── Incidents ────────────────────────────────────────────────────────────────

def create_incident(
    truck_plate: str,
    driver_name: str,
    location: str,
    raw_message: str,
    amount_requested_ngn: int,
    claude_assessment: dict,
    client_name: str = "",
) -> str:
    now = datetime.now(timezone.utc)
    result = get_incidents().insert_one({
        "truck_plate":          truck_plate.upper(),
        "driver_name":          driver_name,
        "location":             location,
        "raw_message":          raw_message,
        "amount_requested_ngn": amount_requested_ngn,
        "claude_assessment":    claude_assessment,
        "issue_summary":        claude_assessment.get("issue_summary", ""),
        "recommended_amount":   claude_assessment.get("recommended_amount_ngn", amount_requested_ngn),
        "client_name":          client_name,
        "status":               "pending",   # pending → approved → resolved
        "amount_approved_ngn":  None,
        "approved_at":          None,
        "resolved_at":          None,
        "resolution_note":      None,
        "created_at":           now,
    })
    # Increment incident count on truck
    get_trucks().update_one(
        {"plate": truck_plate.upper()},
        {"$inc": {"incident_count": 1}},
    )
    return str(result.inserted_id)


def approve_incident(incident_id: str, amount_ngn: int) -> dict | None:
    now = datetime.now(timezone.utc)
    get_incidents().update_one(
        {"_id": ObjectId(incident_id)},
        {"$set": {"status": "approved", "amount_approved_ngn": amount_ngn, "approved_at": now}},
    )
    return _serialise_incident(get_incidents().find_one({"_id": ObjectId(incident_id)}))


def resolve_incident(incident_id: str, note: str = "") -> dict | None:
    now = datetime.now(timezone.utc)
    get_incidents().update_one(
        {"_id": ObjectId(incident_id)},
        {"$set": {"status": "resolved", "resolved_at": now, "resolution_note": note}},
    )
    return _serialise_incident(get_incidents().find_one({"_id": ObjectId(incident_id)}))


def list_incidents(status: str | None = None, limit: int = 50) -> list[dict]:
    query = {}
    if status:
        query["status"] = status
    incidents = list(get_incidents().find(query).sort("created_at", -1).limit(limit))
    return [_serialise_incident(i) for i in incidents if i]


def _serialise_incident(doc: dict | None) -> dict:
    if not doc:
        return {}
    doc["id"] = str(doc.pop("_id"))
    for f in ("created_at", "approved_at", "resolved_at"):
        if hasattr(doc.get(f), "isoformat"):
            doc[f] = doc[f].isoformat()
    return doc
