"""Haggle live path (EYO invention #2).

When a customer haggles over a product the owner has priced, EYO runs the
negotiation core against the secret floor and drafts the next move for the owner
to approve (HITL). If the customer is stuck below the floor (or rounds run out),
EYO holds the line to the customer and pings the OWNER to decide.

Flag-gated on `haggle`, non-blocking. Round state is kept per
(client, contact, product) so the back-and-forth advances. The floor is never
revealed to the customer.

v1 matches the product from the haggle message itself; tying a bare "last price?"
to the product they asked about earlier is a later refinement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from services.eyo_flags import eyo_enabled
from services.haggle_detect import is_haggle, extract_offer, haggle_topic
from services.pricing import get_pricing
from services.haggle import (
    negotiate, haggle_reply_text, owner_escalation_text, owner_haggle_prompt, ESCALATE,
)

log = structlog.get_logger()


def _sessions():
    from database import get_db
    return get_db()["haggle_sessions"]


def _get_state(client_name: str, phone: str, product_key: str) -> Optional[dict]:
    try:
        d = _sessions().find_one(
            {"client_name": client_name, "contact_phone": phone, "product_key": product_key},
            {"state": 1})
        return d.get("state") if d else None
    except Exception:
        return None


def _save_state(client_name: str, phone: str, product_key: str, state: dict) -> None:
    try:
        _sessions().update_one(
            {"client_name": client_name, "contact_phone": phone, "product_key": product_key},
            {"$set": {"state": state, "updated_at": datetime.now(timezone.utc)}},
            upsert=True)
    except Exception as e:
        log.warning("haggle_state_save_failed", error=str(e))


async def maybe_haggle(client_doc: Optional[dict], body_text: str,
                       contact_phone: str, contact_name: Optional[str] = None) -> bool:
    """Best-effort negotiation turn. Returns True if a move was drafted. Never
    raises — must not block inbound handling."""
    try:
        if not client_doc or not body_text:
            return False
        cname = client_doc.get("name")
        if not cname or not eyo_enabled(cname, "haggle"):
            return False
        if not is_haggle(body_text):
            return False
        topic = haggle_topic(body_text)
        if not topic:
            return False
        rules = get_pricing(cname, topic)
        if not rules:
            return False   # no price set for this product — can't negotiate safely

        offer = extract_offer(body_text)
        state = _get_state(cname, contact_phone, rules["product_key"])
        move = negotiate(rules, customer_offer=offer, state=state)
        _save_state(cname, contact_phone, rules["product_key"], move["next_state"])

        # OWNER-FIRST: ping the owner with EYO's suggestion so they set the fair
        # price / option. To avoid spamming on every back-and-forth (they also see
        # each draft in the queue), the proactive ping fires on the FIRST turn of a
        # negotiation and on any below-floor ESCALATE. EYO only suggests — the
        # owner owns the number; nothing reaches the customer until they approve.
        _alert_owner = (move["action"] == ESCALATE) or (move.get("round") == 1)
        if _alert_owner and client_doc.get("owner_phone"):
            try:
                from tools.outreach import send_whatsapp_for_client
                if move["action"] == ESCALATE:
                    alert = owner_escalation_text(move, contact_name, offer,
                                                  rules["floor_price"])
                else:
                    alert = owner_haggle_prompt(move, contact_name, offer,
                                                rules.get("product"))
                await send_whatsapp_for_client(
                    phone=client_doc["owner_phone"], message=alert, client_doc=client_doc)
            except Exception as e:
                log.warning("haggle_owner_alert_failed", error=str(e))

        # Customer-facing move (neutral holding line on escalate) -> HITL, where
        # the owner can edit the price before it sends. That's the flexibility.
        from tools.hitl import queue_draft
        queue_draft(
            contact_id=contact_phone,
            contact_name=contact_name or "",
            vertical="general",
            channel="whatsapp",
            message=haggle_reply_text(move),
            phone=contact_phone,
            client_name=cname,
            source="haggle",          # transactional — skips the prospecting gate
            inbound_context=body_text,
        )
        log.info("haggle_move", client=cname, action=move["action"],
                 product=rules["product_key"])
        return True
    except Exception as e:
        log.warning("haggle_failed", error=str(e))
        return False
