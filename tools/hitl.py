"""
HITL (Human-in-the-Loop) — approval queue for outreach drafts.
Campaign generates messages → stored as pending → owner approves via dashboard.
Nothing goes out without a human tap.

Drafts expire after DRAFT_EXPIRY_HOURS (default 72h). Expired drafts are
auto-skipped on approval attempt to prevent stale messages going out.

Brief Gate:
  Outbound prospecting (BYO Leads, SDR/Maps/Apollo/social discovery, Closer
  outreach) is hard-blocked unless the client's BusinessBrief passes the
  completeness gate. Transactional drafts (invoice, rent, debt, payroll,
  fleet) are warn-only — the chase can still go out with a thin brief
  because the customer relationship already exists.
"""
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from database import get_db
import structlog

DRAFT_EXPIRY_HOURS = 72

# Sources that REQUIRE a complete brief before drafts can be queued.
# Anything not in this set is treated as transactional (warn-only).
_PROSPECTING_SOURCES = {
    "maps", "apollo", "social", "byo_leads",
    "outreach", "closer", "discovery", "campaign",
}

log = structlog.get_logger()


class BriefIncompleteError(Exception):
    """Raised when an outbound prospecting draft is queued for a client whose
    BusinessBrief is missing required fields. The HITL gate is the chokepoint —
    callers should surface the message to the user, not silently drop."""

    def __init__(self, client_name: str, blockers: list[str], score: int, missing: list[str]):
        self.client_name = client_name
        self.blockers = blockers
        self.score = score
        self.missing = missing
        super().__init__(
            f"Brief incomplete for '{client_name}' — missing {', '.join(blockers)}. "
            f"Health {score}/10. Outreach blocked until brief is finished."
        )


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
    source: str = "maps",           # "maps" | "social" | "byo_leads" | "invoice" | ...
    platform: str | None = None,    # "instagram" | "twitter" | "facebook"
    post_context: str | None = None, # the triggering post/tweet text
    profile_url: str | None = None,
    client_name: str | None = None, # required for prospecting gate; optional for transactional
) -> str:
    """Store a generated message as a pending approval. Returns approval _id.

    Raises BriefIncompleteError if `source` is a prospecting channel
    AND `client_name` is provided AND the client's BusinessBrief has
    blockers. Transactional sources (invoice, debt, rent, etc.) skip
    the gate but log a warning so we still see thin briefs.
    """
    _enforce_brief_gate(source=source, client_name=client_name)

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


def _enforce_brief_gate(*, source: str, client_name: str | None) -> None:
    """The choke-point that stops outreach firing when we don't yet understand the client.

    - Prospecting source + known client_name + brief blockers → raise.
    - Prospecting source + no client_name → warn (caller wasn't gate-aware).
    - Transactional source → warn-only on thin brief, never block.
    """
    is_prospecting = source in _PROSPECTING_SOURCES
    if not client_name:
        if is_prospecting:
            log.warning("brief_gate_skipped_no_client_name", source=source)
        return

    # Late import to avoid cycles at module load.
    try:
        from services.brief import brief_health
    except Exception as e:
        log.warning("brief_gate_module_missing", error=str(e))
        return

    health = brief_health(client_name=client_name)
    blockers = health.get("blockers") or []

    if is_prospecting and blockers:
        log.warning(
            "brief_gate_blocked",
            client=client_name,
            source=source,
            blockers=blockers,
            score=health.get("score"),
        )
        raise BriefIncompleteError(
            client_name=client_name,
            blockers=blockers,
            score=int(health.get("score") or 0),
            missing=health.get("missing") or [],
        )

    if blockers:  # transactional path with thin brief — log only
        log.info(
            "brief_gate_warn",
            client=client_name,
            source=source,
            blockers=blockers,
            score=health.get("score"),
        )


def _update_status(approval_id: str, status: str) -> dict | None:
    col = get_approvals()
    col.update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {"status": status, "actioned_at": datetime.now(timezone.utc)}},
    )
    return col.find_one({"_id": ObjectId(approval_id)})
