"""Email inbound -> the EYO brain -> a HITL email draft.

A customer emails the client's connected mailbox; Unipile delivers it to our
webhook; this routes it onto the SAME brain WhatsApp uses (classify -> draft in
the owner's voice) and queues the reply for approval with channel="email".
Nothing sends until the owner taps approve — same HITL rule as every channel.

Outbound send-on-approve from the client's own mailbox is a follow-up (the send
dispatcher currently sends email from ReachNG's account, not the client's).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger()


def _db():
    from database import get_db
    return get_db()


def _client_for_account(account_id: str) -> Optional[dict]:
    if not account_id:
        return None
    return _db()["clients"].find_one(
        {"email_account_id": account_id, "active": True})


def handle_inbound_email(*, account_id: str, from_email: str,
                         from_name: Optional[str] = None,
                         subject: Optional[str] = None,
                         body: str = "", client: Optional[dict] = None) -> bool:
    """Store the inbound email, draft a reply via the brain, queue it HITL.

    `client` may be passed directly (the IMAP poller already has the doc);
    otherwise we resolve it by account_id (the Unipile path). Returns True if a
    draft was queued. Best-effort, never raises.
    """
    try:
        if not from_email or not body:
            return False
        client = client or _client_for_account(account_id)
        if not client:
            log.info("email_inbound_no_client", account_id=account_id)
            return False
        cname = client["name"]
        vertical = client.get("vertical") or "general"
        now = datetime.now(timezone.utc)

        # Persist the inbound (its own collection; unified-customer linking is a
        # later phase). No PII in logs.
        _db()["email_messages"].insert_one({
            "client_name": cname,
            "account_id":  account_id,
            "direction":   "inbound",
            "from_email":  from_email,
            "from_name":   from_name,
            "subject":     subject,
            "body":        body,
            "received_at": now,
        })

        # Classify intent (reuse the WhatsApp classifier — channel-agnostic).
        intent = "question"
        try:
            from services.inbound_classifier import classify_inbound
            cls = classify_inbound(body)
            intent = (cls.get("intent") if isinstance(cls, dict) else None) or "question"
        except Exception as e:
            log.warning("email_classify_failed", error=str(e))

        # Draft a reply in the owner's voice (brain already takes channel=).
        try:
            from agent.brain import generate_auto_reply_draft
            draft = generate_auto_reply_draft(
                original_message="",
                their_reply=body,
                business_name=cname,
                vertical=vertical,
                intent=intent,
                channel="email",
            )
        except Exception as e:
            log.warning("email_draft_failed", error=str(e))
            return False
        if not draft:
            return False

        # Queue for approval — channel email, with the reply subject + address.
        from tools.hitl import queue_draft
        queue_draft(
            contact_id=from_email,
            contact_name=from_name or from_email,
            vertical=vertical,
            channel="email",
            message=draft,
            subject=(f"Re: {subject}" if subject else "Re: your message"),
            email=from_email,
            client_name=cname,
            source="email_inbound",   # transactional — skips the prospecting gate
            inbound_context=body,
        )
        log.info("email_inbound_drafted", client=cname, intent=intent)

        # Radar spans channels: capture email demand too (flag-gated, non-blocking).
        try:
            from services.demand_intel import maybe_capture_demand
            maybe_capture_demand(client, body, from_email)
        except Exception:
            pass

        # Identity: if the email carries a phone we already talk to on WhatsApp,
        # auto-link them as one customer; otherwise suggest the link for the owner.
        try:
            from services.identity import (
                extract_phone_from_text, link_identities, suggest_link,
                linked_phone_for_email,
            )
            phone = extract_phone_from_text(body)
            if phone and not linked_phone_for_email(cname, from_email):
                known = _db()["contacts"].find_one(
                    {"client_name": cname, "phone": {"$regex": phone[-10:]}}, {"_id": 1})
                if known:
                    link_identities(cname, phone, from_email, source="hard_signal")
                else:
                    suggest_link(cname, phone, from_email, reason="phone in email")
        except Exception:
            pass

        return True
    except Exception as e:
        log.warning("email_inbound_failed", error=str(e))
        return False
