"""
AI Loan Officer — MongoDB persistence layer.

Collection: loan_applications
"""
from datetime import datetime, timezone
from bson import ObjectId
from database.mongo import get_db
import structlog

log = structlog.get_logger()

COLLECTION = "loan_applications"


def _db():
    return get_db()[COLLECTION]


def ensure_indexes():
    col = _db()
    col.create_index("mfb_client_name")
    col.create_index("status")
    col.create_index([("created_at", -1)])
    col.create_index("applicant_name")
    col.create_index("decision")


def save_application(
    app: dict,
    score: dict,
    memo_html: str,
    mfb_client_name: str,
) -> str:
    """
    Persist a scored loan application.
    Returns the inserted _id as a string.
    """
    doc = {
        "mfb_client_name": mfb_client_name,
        "status":          _derive_status(score.get("decision", "Decline")),
        "created_at":      datetime.now(timezone.utc),
        "updated_at":      datetime.now(timezone.utc),

        # Application inputs
        "application": app,

        # Scoring output
        "risk_band":              score.get("risk_band"),
        "decision":               score.get("decision"),
        "confidence":             score.get("confidence"),
        "recommended_amount_ngn": score.get("recommended_amount_ngn"),
        "recommended_tenure_months": score.get("recommended_tenure_months"),
        "recommended_rate_pct":   score.get("recommended_rate_pct"),
        "conditions":             score.get("conditions", []),
        "red_flags":              score.get("red_flags", []),
        "strengths":              score.get("strengths", []),
        "rationale":              score.get("rationale"),
        "officer_action":         score.get("officer_action"),
        "factors":                score.get("factors", {}),
        "computed":               score.get("computed", {}),
        "hard_decline_triggered": score.get("hard_decline_triggered", False),

        # Memo
        "memo_html": memo_html,

        # Officer override fields (populated later if needed)
        "officer_override":       None,
        "override_reason":        None,
        "override_by":            None,
        "override_at":            None,
    }
    result = _db().insert_one(doc)
    _id = str(result.inserted_id)
    log.info("loan_application_saved",
             id=_id,
             applicant=app.get("applicant_name"),
             band=score.get("risk_band"),
             decision=score.get("decision"))
    return _id


def get_application(application_id: str) -> dict | None:
    try:
        doc = _db().find_one({"_id": ObjectId(application_id)})
    except Exception:
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_applications(
    mfb_client_name: str | None = None,
    status: str | None = None,
    decision: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query = {}
    if mfb_client_name:
        query["mfb_client_name"] = mfb_client_name
    if status:
        query["status"] = status
    if decision:
        query["decision"] = decision

    docs = list(
        _db()
        .find(query, {"memo_html": 0})  # exclude large HTML from list view
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def count_applications(
    mfb_client_name: str | None = None,
    status: str | None = None,
) -> int:
    query = {}
    if mfb_client_name:
        query["mfb_client_name"] = mfb_client_name
    if status:
        query["status"] = status
    return _db().count_documents(query)


def officer_override(
    application_id: str,
    override_decision: str,
    reason: str,
    officer_name: str,
) -> bool:
    """Allow a loan officer to override the AI decision with audit trail."""
    result = _db().update_one(
        {"_id": ObjectId(application_id)},
        {"$set": {
            "officer_override":  override_decision,
            "override_reason":   reason,
            "override_by":       officer_name,
            "override_at":       datetime.now(timezone.utc),
            "status":            _derive_status(override_decision),
            "updated_at":        datetime.now(timezone.utc),
        }},
    )
    return result.modified_count > 0


def queue_stats(mfb_client_name: str | None = None) -> dict:
    """Counts by decision and status for the officer dashboard."""
    match = {"mfb_client_name": mfb_client_name} if mfb_client_name else {}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$decision",
            "count": {"$sum": 1},
        }},
    ]
    by_decision = {d["_id"]: d["count"] for d in _db().aggregate(pipeline)}

    pipeline2 = [
        {"$match": match},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    by_status = {d["_id"]: d["count"] for d in _db().aggregate(pipeline2)}

    return {
        "total":    sum(by_decision.values()),
        "approve":  by_decision.get("Approve", 0),
        "refer":    by_decision.get("Refer", 0),
        "decline":  by_decision.get("Decline", 0),
        "pending_review": by_status.get("pending_review", 0),
        "disbursed":      by_status.get("disbursed", 0),
    }


def _derive_status(decision: str) -> str:
    return {
        "Approve": "approved",
        "Refer":   "pending_review",
        "Decline": "declined",
    }.get(decision, "pending_review")
