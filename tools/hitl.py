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
import asyncio
import concurrent.futures
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


def _run_async(coro):
    """Run an async coroutine from sync code, regardless of whether a loop is already running."""
    try:
        asyncio.get_running_loop()
        # We're inside an async context — run in a thread to avoid loop conflict
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=25)
    except RuntimeError:
        return asyncio.run(coro)


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
    inbound_context: str | None = None, # inbound message that triggered this draft (for autopilot classifier)
    classification: dict | None = None, # emotion/stage/urgency read from inbound_classifier (T0.2)
) -> str:
    """Store a generated message as a pending approval. Returns approval _id.

    If the client has autopilot=True and the draft passes the safety classifier,
    sends immediately via Unipile/Meta and stores with status=auto_sent.
    Otherwise queues as pending for human approval.

    Raises BriefIncompleteError if `source` is a prospecting channel
    AND `client_name` is provided AND the client's BusinessBrief has
    blockers. Transactional sources (invoice, debt, rent, etc.) skip
    the gate but log a warning so we still see thin briefs.
    """
    _enforce_brief_gate(source=source, client_name=client_name)
    _enforce_account_caps(source=source, client_name=client_name)

    # ── Autopilot check ───────────────────────────────────────────────────────
    if client_name and _is_autopilot_enabled(client_name):
        sent = _try_autopilot_send(
            contact_id=contact_id,
            contact_name=contact_name,
            client_name=client_name,
            vertical=vertical,
            channel=channel,
            message=message,
            subject=subject,
            phone=phone,
            email=email,
            source=source,
            inbound_context=inbound_context,
        )
        if sent:
            return sent  # Returns the stored doc _id — no human needed

    col = get_approvals()
    result = col.insert_one({
        "contact_id":    ObjectId(contact_id),
        "contact_name":  contact_name,
        "client_name":   client_name,
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
        # T0.2 — emotion / stage / urgency read of the inbound that triggered this draft
        "classification": classification,
        "escalated":      bool(classification and classification.get("escalate")),
    })
    approval_id = str(result.inserted_id)
    log.info("draft_queued", contact=contact_name, channel=channel, source=source)

    # ── Sales Alerter: real-time owner ping on hot/closing/escalated leads ───
    # Fire-and-forget — never block the draft queue if the alert misbehaves.
    if classification and client_name:
        try:
            from services.sales_alerter import alert_owner_about_draft
            import asyncio, re as _re
            # Resolve client_id from name (kept light — single indexed lookup)
            _client_doc = get_db()["clients"].find_one(
                {"name": {"$regex": f"^{_re.escape(client_name)}$", "$options": "i"}},
                {"_id": 1},
            )
            if _client_doc and phone:
                async def _fire():
                    try:
                        await alert_owner_about_draft(
                            client_id=str(_client_doc["_id"]),
                            contact_phone=phone,
                            contact_name=contact_name or "lead",
                            classification=classification,
                            suggested_reply=message or "",
                            inbound_excerpt=inbound_context,
                            approval_id=approval_id,
                        )
                    except Exception as _e:
                        log.warning("sales_alert_fire_failed", error=str(_e))
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(_fire())
                    else:
                        loop.run_until_complete(_fire())
                except RuntimeError:
                    asyncio.run(_fire())
        except Exception as _e:
            log.warning("sales_alert_dispatch_failed", error=str(_e))

    return approval_id


def get_pending(vertical: str | None = None, limit: int = 50) -> list[dict]:
    """Return all non-expired pending approvals, optionally filtered by vertical."""
    now = datetime.now(timezone.utc)
    query = {
        "status": ApprovalStatus.PENDING,
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }
    if vertical:
        query["vertical"] = vertical
    # Sort: escalated first (1 > 0), then highest-urgency first via a
    # computed bucket, then newest first. Owner sees angry/on_fire/closing
    # leads at the top of their queue regardless of arrival time.
    URGENCY_RANK = {"on_fire": 3, "hot": 2, "interested": 1, "idle": 0}
    docs = list(get_approvals().find(query))
    def _rank(d):
        cls = d.get("classification") or {}
        return (
            1 if d.get("escalated") else 0,
            URGENCY_RANK.get(cls.get("urgency"), 0),
            d.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
        )
    docs.sort(key=_rank, reverse=True)
    return docs[:limit]


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


def _enforce_account_caps(*, source: str, client_name: str | None) -> None:
    """Apply daily-cap + paused-flag gates for prospecting drafts only.
    Transactional sources skip caps because chase volume is driven by debtors,
    not by us — limiting it would defeat the purpose."""
    if not client_name or source not in _PROSPECTING_SOURCES:
        return
    try:
        from tools.account_guard import enforce_account_caps
    except Exception as e:
        log.warning("account_guard_module_missing", error=str(e))
        return
    enforce_account_caps(client_name=client_name)


def _update_status(approval_id: str, status: str) -> dict | None:
    col = get_approvals()
    col.update_one(
        {"_id": ObjectId(approval_id)},
        {"$set": {"status": status, "actioned_at": datetime.now(timezone.utc)}},
    )
    return col.find_one({"_id": ObjectId(approval_id)})


# ─── Autopilot helpers ────────────────────────────────────────────────────────

def _is_autopilot_enabled(client_name: str) -> bool:
    """Check if client has autopilot mode active."""
    try:
        from api.clients import get_clients
        client = get_clients().find_one(
            {"name": {"$regex": f"^{client_name}$", "$options": "i"}},
            {"autopilot": 1},
        )
        return bool(client and client.get("autopilot"))
    except Exception as e:
        log.warning("autopilot_check_failed", client=client_name, error=str(e))
        return False


def _try_autopilot_send(
    *,
    contact_id: str,
    contact_name: str,
    client_name: str,
    vertical: str,
    channel: str,
    message: str,
    subject: str | None,
    phone: str | None,
    email: str | None,
    source: str,
    inbound_context: str | None,
) -> str | None:
    """
    Run the autopilot classifier. If SAFE_TO_SEND, dispatch the message immediately,
    log it as auto_sent, and return the stored doc _id. Returns None if NEEDS_HUMAN.
    """
    try:
        from agent.brain import classify_for_autopilot
        result = classify_for_autopilot(
            draft_message=message,
            inbound_context=inbound_context,
            channel=channel,
        )
    except Exception as e:
        log.warning("autopilot_classify_error", error=str(e))
        return None

    verdict = result.get("verdict", "NEEDS_HUMAN")
    reason  = result.get("reason", "")

    if verdict != "SAFE_TO_SEND":
        log.info("autopilot_escalated", contact=contact_name, reason=reason)
        # Still queue — but tag so dashboard shows escalation reason
        col = get_approvals()
        res = col.insert_one({
            "contact_id":        ObjectId(contact_id),
            "contact_name":      contact_name,
            "client_name":       client_name,
            "vertical":          vertical,
            "channel":           channel,
            "message":           message,
            "subject":           subject,
            "phone":             phone,
            "email":             email,
            "source":            source,
            "status":            ApprovalStatus.PENDING,
            "escalation_reason": reason,
            "autopilot_checked": True,
            "created_at":        datetime.now(timezone.utc),
            "expires_at":        datetime.now(timezone.utc) + timedelta(hours=DRAFT_EXPIRY_HOURS),
            "actioned_at":       None,
            "edited_message":    None,
        })
        return None  # Signal caller to not store a second record

    # Dispatch
    from api.clients import get_clients
    client_doc = get_clients().find_one(
        {"name": {"$regex": f"^{client_name}$", "$options": "i"}}
    ) or {}

    send_result: dict = {"success": False}
    try:
        if channel == "whatsapp" and phone:
            from tools.outreach import send_whatsapp_for_client
            send_result = _run_async(send_whatsapp_for_client(phone, message, client_doc))
        elif channel == "email" and email:
            from tools.outreach import send_email
            send_result = _run_async(send_email(email, subject or "Message from ReachNG", message))
    except Exception as e:
        log.error("autopilot_send_failed", contact=contact_name, channel=channel, error=str(e))
        return None  # Fall back to HITL queue

    if not send_result.get("success"):
        log.warning("autopilot_send_unsuccessful", contact=contact_name, detail=send_result)
        return None

    # Log as sent
    col = get_approvals()
    res = col.insert_one({
        "contact_id":    ObjectId(contact_id),
        "contact_name":  contact_name,
        "client_name":   client_name,
        "vertical":      vertical,
        "channel":       channel,
        "message":       message,
        "subject":       subject,
        "phone":         phone,
        "email":         email,
        "source":        source,
        "status":        "auto_sent",
        "send_result":   send_result,
        "created_at":    datetime.now(timezone.utc),
        "actioned_at":   datetime.now(timezone.utc),
        "edited_message": None,
    })
    log.info("autopilot_sent", contact=contact_name, channel=channel, message_id=send_result.get("message_id"))
    return str(res.inserted_id)
