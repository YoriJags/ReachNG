"""
MongoDB store for legal reviews — history per firm, retrievable by review ID.
"""
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
import structlog

log = structlog.get_logger()


def get_reviews_col():
    return get_db()["legal_reviews"]


def ensure_legal_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_reviews_col()
    col.create_index([("firm_name", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])
    col.create_index([("status", ASCENDING)])


def save_review(
    firm_name: str,
    filename: str,
    clauses: dict,
    memo: str,
    overall_risk: str,
) -> str:
    """Persist a completed review. Returns the review ID."""
    result = get_reviews_col().insert_one({
        "firm_name":    firm_name,
        "filename":     filename,
        "clauses":      clauses,
        "memo":         memo,
        "overall_risk": overall_risk,
        "status":       "complete",
        "created_at":   datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def get_review(review_id: str) -> dict | None:
    doc = get_reviews_col().find_one({"_id": ObjectId(review_id)})
    if doc:
        doc["id"] = str(doc.pop("_id"))
        if hasattr(doc.get("created_at"), "isoformat"):
            doc["created_at"] = doc["created_at"].isoformat()
    return doc


def list_reviews(firm_name: str | None = None, limit: int = 20) -> list[dict]:
    query = {}
    if firm_name:
        query["firm_name"] = {"$regex": firm_name, "$options": "i"}
    docs = list(
        get_reviews_col()
        .find(query, {"clauses": 0})  # exclude heavy clauses from list
        .sort("created_at", -1)
        .limit(limit)
    )
    for d in docs:
        d["id"] = str(d.pop("_id"))
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
    return docs
