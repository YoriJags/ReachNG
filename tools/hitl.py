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

# Cold-discovery sources = strangers we found, with no prior relationship or
# consent. Cold WhatsApp to these is not allowed (cold outreach is email-only);
# they may only be WhatsApp'd after they message in first (24h session window).
_COLD_DISCOVERY_SOURCES = {"maps", "apollo", "discovery", "social"}

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


def _client_transport(client_name: str | None) -> str | None:
    """Resolve a client's WhatsApp transport: "meta" | "unipile" | None.

    Lets EYO adjust behaviour per transport (Meta enforces the 24h template
    window; Unipile is free-form + caps). Defaults to "unipile" (the system
    default) when the client exists without an explicit provider; None only when
    there's no client_name or the lookup fails.
    """
    if not client_name:
        return None
    try:
        from api.clients import get_clients
        c = get_clients().find_one(
            {"name": {"$regex": f"^{client_name}$", "$options": "i"}},
            {"whatsapp_provider": 1},
        )
        if not c:
            return None
        return (c.get("whatsapp_provider") or "unipile").lower()
    except Exception as e:
        log.warning("client_transport_lookup_failed", client=client_name, error=str(e))
        return None


class OutreachConsentMissing(Exception):
    """Raised when a cold-discovery contact would be messaged on WhatsApp without
    consent and without a recent inbound. Cold WhatsApp is not allowed — first
    contact goes by email, or the contact must message in first."""

    def __init__(self, contact_name: str, source: str):
        self.contact_name = contact_name
        self.source = source
        super().__init__(
            f"WhatsApp outreach to '{contact_name}' (source: {source}) blocked: "
            f"no prior relationship and no inbound in the last 24h. Cold WhatsApp "
            f"is not allowed — use email for first contact, or wait for them to "
            f"message in."
        )


def _enforce_whatsapp_consent_gate(
    *, source: str, channel: str, has_open_session: bool, contact_name: str
) -> None:
    """Protection floor: never cold-WhatsApp a stranger.

    Only applies to WhatsApp drafts from a cold-discovery source. If there was a
    customer-initiated inbound in the last 24h (`has_open_session` True), the send
    is allowed. Otherwise it is blocked. Transport-agnostic — cold WhatsApp is
    email-only whether the client runs on Meta or Unipile.

    Transactional sources, BYO leads (client-attested consent), and all email
    are unaffected.
    """
    if channel != "whatsapp" or source not in _COLD_DISCOVERY_SOURCES:
        return
    if has_open_session:
        return  # open 24h session (they messaged us) — allowed
    raise OutreachConsentMissing(contact_name=contact_name, source=source)


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

    # ── Transport-aware session / template window ──────────────────────────
    # has_open_session = the customer messaged us within 24h (transport-agnostic;
    #   drives the cold-WhatsApp consent floor below).
    # requires_template is a META-only concept: Meta forbids non-template
    #   outbound outside that 24h window. Unipile has no template rule (free-form
    #   anytime, gated instead by warm-up/caps), so it never "requires a template".
    has_open_session = False
    try:
        if channel == "whatsapp" and phone and client_name:
            last_in = get_db()["inbound_messages"].find_one(
                {"client_name": client_name, "sender_phone": phone,
                 "received_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)}},
                {"_id": 1},
            )
            has_open_session = bool(last_in)
    except Exception:
        pass

    transport = _client_transport(client_name)  # "meta" | "unipile" | None
    requires_template = (
        channel == "whatsapp" and transport == "meta" and not has_open_session
    )

    # ── Consent floor: never cold-WhatsApp a stranger ──────────────────────────
    # Cold-discovery WhatsApp with no open 24h session is blocked here (cold
    # outreach is email-only), regardless of transport. Raises OutreachConsentMissing
    # for the caller to surface — same chokepoint pattern as the brief gate.
    _enforce_whatsapp_consent_gate(
        source=source, channel=channel,
        has_open_session=has_open_session, contact_name=contact_name,
    )

    # ── Tone scrub ────────────────────────────────────────────────────────────
    # Strip casual endearments ("babe", "love", "dear" etc.) that the drafter
    # may have generated despite the never-say rule in the system prompt.
    # Centralised at the queue_draft boundary so every drafter inherits it.
    try:
        from tools.tone import scrub_endearments
        message = scrub_endearments(message)
    except Exception:  # tone scrub must never block a send
        pass

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

    # ── Risk score — deterministic, no LLM call ─────────────────────────────
    try:
        from services.draft_risk import score_draft
        _risk = score_draft(
            message=message,
            classification=classification,
            inbound_context=inbound_context,
            vertical=vertical,
            escalated=bool(classification and classification.get("escalate")),
        )
    except Exception:
        _risk = {"confidence": "medium", "score": 50, "tags": []}

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
        "transport":     transport,   # "meta" | "unipile" | None — reply on the same rail
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
        # P1 quick-win — deterministic risk read so the operator knows which drafts to eyeball
        "risk":           _risk,
        # WhatsApp ban defence — flag drafts outside the 24h session window so
        # the operator knows a template send is required by Meta's policy.
        "requires_template": requires_template,
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
    updated = _update_status(approval_id, ApprovalStatus.APPROVED)
    _open_outcome_safe(updated or draft)
    _capture_quote_safe(updated or draft)
    return updated


def skip_draft(approval_id: str) -> dict | None:
    """Mark as skipped. Will not be sent."""
    return _update_status(approval_id, ApprovalStatus.SKIPPED)


def edit_draft(approval_id: str, new_message: str) -> dict | None:
    """Update message text and mark as approved with edited content.

    Persists the original message as `original_message` (idempotent — set
    only on first edit) so the never-say tone-loop job can diff edits over
    time. See services/edit_tone_loop.py.
    """
    col = get_approvals()
    now = datetime.now(timezone.utc)
    existing = col.find_one({"_id": ObjectId(approval_id)}, {"message": 1, "original_message": 1})
    patch: dict = {
        "status":         ApprovalStatus.EDITED,
        "edited_message": new_message,
        "actioned_at":    now,
    }
    # Preserve the very first version we generated — survives multiple edits.
    if existing and not existing.get("original_message"):
        patch["original_message"] = existing.get("message")

    col.update_one({"_id": ObjectId(approval_id)}, {"$set": patch})
    doc = col.find_one({"_id": ObjectId(approval_id)})

    # Tone-loop hook: best-effort, never blocks the edit
    try:
        from services.edit_tone_loop import record_edit
        record_edit(doc, new_message=new_message)
    except Exception as e:
        log.warning("edit_tone_loop_record_failed", error=str(e))

    _open_outcome_safe(doc)
    _capture_quote_safe(doc, new_message)
    return doc


def _open_outcome_safe(approval_doc: dict | None) -> None:
    """Best-effort hook into outcome_learning. Never raises — outcome tracking
    failure must not block an approval send."""
    if not approval_doc:
        return
    try:
        from services.outcome_learning import open_outcome_from_approval
        open_outcome_from_approval(approval_doc)
    except Exception as e:
        log.warning("outcome_open_failed", error=str(e))


def _capture_quote_safe(approval_doc: dict | None, message: str | None = None) -> None:
    """Best-effort: if the approved outbound carries a ₦ quote, remember it on the
    contact (`last_quote_ngn`) so pipeline value (money_leak / cashflow) reflects
    real numbers instead of a flat estimate. Never raises."""
    try:
        if not approval_doc:
            return
        text = message or approval_doc.get("message") or ""
        from services.deal_value import parse_money
        m = parse_money(text)
        if not m:
            return
        phone = approval_doc.get("phone") or approval_doc.get("contact_phone")
        if not phone:
            return
        from database import get_db
        q = {"phone": phone}
        cname = approval_doc.get("client_name")
        if cname:
            q["client_name"] = cname
        patch = {
            "last_quote_amount":   m["amount"],
            "last_quote_currency": m["currency"],
            "last_quote_at":       datetime.now(timezone.utc),
        }
        # Only feed the NGN pipeline figure with NGN quotes — never assume FX.
        if m["currency"] == "NGN":
            patch["last_quote_ngn"] = m["amount"]
        get_db()["contacts"].update_one(q, {"$set": patch})
    except Exception as e:
        log.warning("quote_capture_failed", error=str(e))


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

    # ── Send-window floor ─────────────────────────────────────────────────────
    # Hold automated sends outside Africa/Lagos business hours (08:00–20:00).
    # Returning None falls back to the normal HITL queue — the draft is never
    # dropped; the owner can approve it whenever. Human approvals are unaffected.
    try:
        from tools.account_guard import is_within_send_window
        if not is_within_send_window():
            log.info("autopilot_held_outside_send_window", contact=contact_name)
            return None
    except Exception as e:
        log.warning("send_window_check_failed", error=str(e))

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
