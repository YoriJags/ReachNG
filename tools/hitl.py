"""
HITL (Human-in-the-Loop) — approval queue for outreach drafts.
Campaign generates messages → stored as pending → owner approves via dashboard.
Nothing goes out without a human tap.
"""
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
import structlog

log = structlog.get_logger()


def get_approvals():
    return get_db()["pending_approvals"]


def ensure_approval_indexes():
    col = get_approvals()
    from pymongo import ASCENDING, DESCENDING
    col.create_index([("status", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])
    col.create_index([("contact_id", ASCENDING)])


# ─── Status constants ─────────────────────────────────────────────────────────
class ApprovalStatus:
    PENDING  = "pending"
    APPROVED = "approved"
    SKIPPED  = "skipped"
    EDITED   = "edited"


# ─── Queue operations ─────────────────────────────────────────────────────────

def queue_draft(
    contact_id: str,
    contact_name: str,
    vertical: str,
    channel: str,
    message: str,
    subject: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> str:
    """Store a generated message as a pending approval. Returns approval _id."""
    col = get_approvals()
    result = col.insert_one({
        "contact_id": ObjectId(contact_id),
        "contact_name": contact_name,
        "vertical": vertical,
        "channel": channel,
        "message": message,
        "subject": subject,
        "phone": phone,
        "email": email,
        "status": ApprovalStatus.PENDING,
        "created_at": datetime.now(timezone.utc),
        "actioned_at": None,
        "edited_message": None,
    })
    log.info("draft_queued", contact=contact_name, channel=channel)
    return str(result.inserted_id)


def get_pending(vertical: str | None = None, limit: int = 50) -> list[dict]:
    """Return all pending approvals, optionally filtered by vertical."""
    query = {"status": ApprovalStatus.PENDING}
    if vertical:
        query["vertical"] = vertical
    return list(
        get_approvals()
        .find(query)
        .sort("created_at", 1)  # oldest first
        .limit(limit)
    )


def get_approval_stats() -> dict:
    """Summary counts for the dashboard."""
    col = get_approvals()
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    rows = list(col.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


def approve_draft(approval_id: str) -> dict | None:
    """Mark as approved. Returns the approval doc for sending."""
    return _update_status(approval_id, ApprovalStatus.APPROVED)


def skip_draft(approval_id: str) -> dict | None:
    """Mark as skipped. Will not be sent."""
    return _update_status(approval_id, ApprovalStatus.SKIPPED)


def edit_draft(approval_id: str, new_message: str) -> dict | None:
    """Update message text and mark as approved with edited content."""
    col = get_approvals()
    now = datetime.now(timezone.utc)
    col.update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {
            "status": ApprovalStatus.EDITED,
            "edited_message": new_message,
            "actioned_at": now,
        }},
    )
    return col.find_one({"_id": ObjectId(approval_id)})


def _update_status(approval_id: str, status: str) -> dict | None:
    col = get_approvals()
    col.update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {"status": status, "actioned_at": datetime.now(timezone.utc)}},
    )
    return col.find_one({"_id": ObjectId(approval_id)})
