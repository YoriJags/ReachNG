"""Meta IG/Messenger inbound -> the EYO brain -> a HITL draft.

A customer DMs the client's Instagram or Facebook Page; the brain drafts a reply
in the owner's voice; it queues for approval with channel "instagram"/"messenger".
Nothing sends until the owner taps approve. Best-effort, never raises.
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
        {"$or": [{"meta_page_id": account_id}, {"meta_ig_id": account_id}],
         "active": True})


def handle_meta_message(*, channel: str, account_id: str, sender_id: str,
                        text: str, client: Optional[dict] = None) -> bool:
    """Store the DM, draft a reply via the brain, queue it HITL. Returns True if
    a draft was queued."""
    try:
        if not account_id or not sender_id or not text:
            return False
        client = client or _client_for_account(account_id)
        if not client:
            log.info("meta_inbound_no_client", account_id=account_id)
            return False
        cname = client["name"]
        vertical = client.get("vertical") or "general"

        _db()["meta_messages"].insert_one({
            "client_name": cname,
            "channel":     channel,
            "account_id":  account_id,
            "sender_id":   sender_id,
            "direction":   "inbound",
            "text":        text,
            "received_at": datetime.now(timezone.utc),
        })

        intent = "question"
        try:
            from services.inbound_classifier import classify_inbound
            cls = classify_inbound(text)
            intent = (cls.get("intent") if isinstance(cls, dict) else None) or "question"
        except Exception as e:
            log.warning("meta_classify_failed", error=str(e))

        try:
            from agent.brain import generate_auto_reply_draft
            draft = generate_auto_reply_draft(
                original_message="", their_reply=text, business_name=cname,
                vertical=vertical, intent=intent, channel=channel)
        except Exception as e:
            log.warning("meta_draft_failed", error=str(e))
            return False
        if not draft:
            return False

        from tools.hitl import queue_draft
        queue_draft(
            contact_id=sender_id,
            contact_name=sender_id,
            vertical=vertical,
            channel=channel,
            message=draft,
            client_name=cname,
            source="meta_inbound",   # transactional — skips the prospecting gate
            inbound_context=text,
        )
        log.info("meta_inbound_drafted", client=cname, channel=channel, intent=intent)
        return True
    except Exception as e:
        log.warning("meta_inbound_failed", error=str(e))
        return False
