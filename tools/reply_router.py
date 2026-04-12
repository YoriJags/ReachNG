"""
Reply router — polls Unipile for inbound replies and routes them to contacts.
Matches by phone (WhatsApp) or email. Updates contact status to REPLIED.
Runs every 30 minutes via the scheduler.
"""
from datetime import datetime, timezone
from database import get_contacts, get_db
from tools.outreach import check_whatsapp_replies, check_email_replies
from tools.memory import mark_replied, mark_opted_out, Status
from tools.notifier import notify_owner, notify_whatsapp as notify_owner_whatsapp
from agent.brain import classify_reply, generate_auto_reply_draft
import structlog

log = structlog.get_logger()


def get_replies():
    return get_db()["replies"]


async def process_replies() -> dict:
    """
    Poll Unipile for new WhatsApp and email replies.
    Match each reply to a contact. Mark matched contacts as REPLIED.
    Returns summary: {processed, matched, already_seen, unmatched, errors}
    """
    summary = {"processed": 0, "matched": 0, "already_seen": 0, "unmatched": 0, "errors": 0}

    try:
        whatsapp_msgs = await check_whatsapp_replies()
    except Exception as e:
        log.error("reply_poll_whatsapp_failed", error=str(e))
        whatsapp_msgs = []
        summary["errors"] += 1

    try:
        email_msgs = await check_email_replies()
    except Exception as e:
        log.error("reply_poll_email_failed", error=str(e))
        email_msgs = []
        summary["errors"] += 1

    for msg in whatsapp_msgs:
        result = _route_reply(msg, channel="whatsapp")
        _tally(summary, result)

    for msg in email_msgs:
        result = _route_reply(msg, channel="email")
        _tally(summary, result)

    log.info("reply_routing_complete", **summary)
    return summary


def _route_reply(msg: dict, channel: str) -> str:
    """
    Route one inbound message to the right contact.
    Returns: "matched" | "already_seen" | "unmatched" | "error"
    """
    replies = get_replies()

    # Deduplicate by Unipile message ID
    msg_id = msg.get("id") or msg.get("message_id")
    if not msg_id:
        return "error"

    if replies.find_one({"unipile_message_id": msg_id}):
        return "already_seen"

    sender = _extract_sender(msg, channel)
    if not sender:
        return "error"

    contact = _find_contact(sender, channel)
    now = datetime.now(timezone.utc)
    reply_text = (msg.get("text") or msg.get("body") or msg.get("snippet") or "")[:2000]

    # Classify reply intent via Claude Haiku (fast + cheap)
    classification = {"intent": "unknown", "urgency": "low", "summary": reply_text[:100]}
    if contact and reply_text:
        try:
            classification = classify_reply(
                reply_text=reply_text,
                business_name=contact.get("name", ""),
                vertical=contact.get("vertical", ""),
            )
        except Exception as e:
            log.warning("classify_reply_failed", error=str(e))

    # Always store the raw reply + full classification — dashboard + audit trail
    replies.insert_one({
        "unipile_message_id":  msg_id,
        "channel":             channel,
        "sender":              sender,
        "text":                reply_text,
        "contact_id":          contact["_id"] if contact else None,
        "contact_name":        contact.get("name") if contact else None,
        "intent":              classification.get("intent", "unknown"),
        "urgency":             classification.get("urgency", "low"),
        "budget_authority":    classification.get("budget_authority", "unknown"),
        "hot_lead":            classification.get("hot_lead", False),
        "summary":             classification.get("summary", ""),
        "received_at":         now,
    })

    if not contact:
        log.info("reply_unmatched", sender=sender, channel=channel)
        return "unmatched"

    contact_id  = str(contact["_id"])
    intent      = classification.get("intent", "unknown")
    urgency     = classification.get("urgency", "low")
    hot_lead    = classification.get("hot_lead", False)

    # Auto opt-out — act immediately, no manual step needed
    if intent == "opted_out":
        mark_opted_out(contact_id)
        log.info("auto_opted_out", contact=contact.get("name"), sender=sender)
    elif contact.get("status") == Status.CONTACTED:
        mark_replied(contact_id)
        log.info(
            "reply_matched",
            contact=contact.get("name"),
            vertical=contact.get("vertical"),
            intent=intent,
            hot_lead=hot_lead,
            channel=channel,
        )

    import asyncio

    # Hot lead — fire an urgent separate WhatsApp ping to owner immediately
    if hot_lead:
        settings_obj = __import__("config", fromlist=["get_settings"]).get_settings()
        if settings_obj.owner_whatsapp:
            urgent_msg = (
                f"🚨 HOT LEAD — {contact.get('name', sender)}\n"
                f"Vertical: {contact.get('vertical', '').replace('_', ' ').title()}\n"
                f"Channel: {channel.title()}\n"
                f"Budget authority: {classification.get('budget_authority', 'unknown').upper()}\n\n"
                f"Their message:\n\"{reply_text[:300]}\"\n\n"
                f"→ Follow up NOW."
            )
            asyncio.create_task(
                notify_owner_whatsapp(
                    contact_name=contact.get("name", sender),
                    vertical=contact.get("vertical", ""),
                    channel=channel,
                    reply_text=urgent_msg,
                    intent="interested",
                    urgency="high",
                    summary=classification.get("summary", ""),
                )
            )
        log.info("hot_lead_alert_fired", contact=contact.get("name"))

    # Auto-reply draft — queue to HITL for warm intents
    _AUTO_REPLY_INTENTS = {"interested", "question", "price_question"}
    if intent in _AUTO_REPLY_INTENTS and contact:
        try:
            # Find the last outreach message sent to this contact for context
            from database import get_db
            last_outreach = get_db()["outreach"].find_one(
                {"contact_id": contact_id},
                sort=[("sent_at", -1)],
            )
            original_msg = (last_outreach or {}).get("message", "")
            draft = generate_auto_reply_draft(
                original_message=original_msg,
                their_reply=reply_text,
                business_name=contact.get("name", ""),
                vertical=contact.get("vertical", ""),
                intent=intent,
                channel=channel,
            )
            from tools.hitl import queue_draft
            queue_draft(
                contact_id=contact_id,
                contact_name=contact.get("name", ""),
                vertical=contact.get("vertical", ""),
                channel=channel,
                message=draft,
                phone=contact.get("phone"),
                email=contact.get("email"),
                source="auto_reply",
            )
            log.info("auto_reply_draft_queued", contact=contact.get("name"), intent=intent)
        except Exception as e:
            log.warning("auto_reply_draft_failed", error=str(e))

    # Standard notify — both WhatsApp + Slack
    asyncio.create_task(notify_owner(
        contact_name=contact.get("name", sender),
        vertical=contact.get("vertical", ""),
        channel=channel,
        reply_text=reply_text,
        intent=intent,
        urgency=urgency,
        summary=classification.get("summary", ""),
    ))

    return "matched"


def _extract_sender(msg: dict, channel: str) -> str | None:
    """Extract the sender's phone or email from a Unipile message payload."""
    if channel == "whatsapp":
        # Unipile returns attendees list — sender is the one who isn't us
        for attendee in msg.get("attendees", []):
            identifier = (
                attendee.get("identifier")
                or attendee.get("id")
                or attendee.get("phone")
            )
            if identifier and identifier != msg.get("account_id"):
                return identifier
        return msg.get("from_attendee") or msg.get("sender_id")

    elif channel == "email":
        from_field = msg.get("from") or {}
        if isinstance(from_field, dict):
            return from_field.get("identifier") or from_field.get("address")
        if isinstance(from_field, str):
            return from_field

    return None


def _find_contact(sender: str, channel: str) -> dict | None:
    """Look up contact by phone (WhatsApp) or email."""
    contacts = get_contacts()

    if channel == "whatsapp":
        # Normalise — Unipile may return with or without leading +
        normalised = sender if sender.startswith("+") else f"+{sender}"
        return (
            contacts.find_one({"phone": normalised})
            or contacts.find_one({"phone": sender.lstrip("+")})
        )

    elif channel == "email":
        return contacts.find_one({"email": sender.lower()})

    return None


def _tally(summary: dict, result: str):
    summary["processed"] += 1
    if result in summary:
        summary[result] += 1
