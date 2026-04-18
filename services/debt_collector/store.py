"""Debt Collector — MongoDB persistence layer."""
from datetime import datetime, timezone
from bson import ObjectId
from database.mongo import get_db
import structlog

log = structlog.get_logger()
COLLECTION = "debt_cases"


def _db():
    return get_db()[COLLECTION]


def ensure_indexes():
    col = _db()
    col.create_index("client_name")
    col.create_index("status")
    col.create_index("debtor_name")
    col.create_index([("original_due_date", 1)])
    col.create_index([("created_at", -1)])


def create_case(
    client_name: str,
    debtor_name: str,
    debtor_business: str,
    debtor_phone: str,
    amount_ngn: float,
    description: str,
    original_due_date: datetime,
    relationship_context: str = "",
) -> str:
    doc = {
        "client_name":          client_name,
        "debtor_name":          debtor_name,
        "debtor_business":      debtor_business,
        "debtor_phone":         debtor_phone,
        "amount_ngn":           amount_ngn,
        "description":          description,
        "original_due_date":    original_due_date,
        "relationship_context": relationship_context,
        "status":               "active",
        "current_stage":        "reminder",
        "reminder_count":       0,
        "last_reminder_at":     None,
        "prior_responses":      "",
        "paid_at":              None,
        "created_at":           datetime.now(timezone.utc),
        "updated_at":           datetime.now(timezone.utc),
    }
    result = _db().insert_one(doc)
    _id = str(result.inserted_id)
    log.info("debt_case_created", id=_id, debtor=debtor_name, amount=amount_ngn)
    return _id


def get_due_cases() -> list[dict]:
    """Return active cases due for their next reminder."""
    now = datetime.now(timezone.utc)
    docs = list(
        _db().find({
            "status": "active",
            "$or": [
                {"last_reminder_at": None},
                {"last_reminder_at": {"$lt": datetime(now.year, now.month, now.day, tzinfo=timezone.utc)}},
            ],
        })
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def record_reminder(case_id: str, stage: str, message: str):
    _db().update_one(
        {"_id": ObjectId(case_id)},
        {"$set": {
            "current_stage":    stage,
            "last_reminder_at": datetime.now(timezone.utc),
            "updated_at":       datetime.now(timezone.utc),
        }, "$inc": {"reminder_count": 1}},
    )


def mark_paid(case_id: str):
    _db().update_one(
        {"_id": ObjectId(case_id)},
        {"$set": {
            "status":     "paid",
            "paid_at":    datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )


def list_cases(client_name: str | None = None, status: str = "active") -> list[dict]:
    query = {"status": status}
    if client_name:
        query["client_name"] = client_name
    docs = list(_db().find(query).sort("original_due_date", 1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs
