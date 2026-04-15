"""
HITL (Human-in-the-Loop) — approval queue for outreach drafts.
Campaign generates messages → stored as pending → owner approves via dashboard.
Nothing goes out without a human tap.

Drafts expire after DRAFT_EXPIRY_HOURS (default 72h). Expired drafts are
auto-skipped on approval attempt to prevent stale messages going out.
"""
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from database import get_db
import structlog

DRAFT_EXPIRY_HOURS = 72

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
    source: str = "maps",           # "maps" | "social"
    platform: str | None = None,    # "instagram" | "twitter" | "facebook"
    post_context: str | None = None, # the triggering post/tweet text
    profile_url: str | None = None,
) -> str:
    """Store a generated message as a pending approval. Returns approval _id."""
    col = get_approvals()
    result = col.insert_one({
        "contact_id":    ObjectId(contact_id),
        "contact_name":  contact_name,
        "vertical":      vertical,
        "channel":       channel,
        "message":       message,
        "subject":       subject,
        "phone":         phone,
        "email":         email,
        "source":        source,
        "platform":      platform,
        "post_context":  post_context,
        "profile_url":   profile_url,
        "status":        ApprovalStatus.PENDING,
        "created_at":    datetime.now(timezone.utc),
        "expires_at":    datetime.now(timezone.utc) + timedelta(hours=DRAFT_EXPIRY_HOURS),
        "actioned_at":   None,
        "edited_message": None,
    })
    log.info("draft_queued", contact=contact_name, channel=channel, source=source)
    return str(result.inserted_id)


def get_pending(vertical: str | None = None, limit: int = 50) -> list[dict]:
    """Return all non-expired pending approvals, optionally filtered by vertical."""
    now = datetime.now(timezone.utc)
    query = {
        "status": ApprovalStatus.PENDING,
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }
    if vertical:
        query["vertical"] = vertical
    return list(
        get_approvals()
        .find(query)
        .sort("created_at", -1)  # newest first
        .limit(limit)
    )


def get_approval_stats() -> dict:
    """Summary counts for the dashboard."""
    col = get_approvals()
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    rows = list(col.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


def approve_draft(approval_id: str) -> dict | None:
    """Mark as approved. Returns the approval doc for sending. Returns None if expired."""
    col = get_approvals()
    draft = col.find_one({"_id": ObjectId(approval_id)})
    if not draft:
        return None
    expires_at = draft.get("expires_at")
    if expires_at and datetime.now(timezone.utc) > expires_at:
        _update_status(approval_id, ApprovalStatus.SKIPPED)
        log.warning("draft_expired_on_approve", approval_id=approval_id, contact=draft.get("contact_name"))
        return None
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
