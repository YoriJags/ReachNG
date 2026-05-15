"""
Sales Alerter — real-time owner ping when a hot/closing lead lands.

Why this exists
---------------
The HITL queue is fine when the operator is *at* the dashboard. But the moment
a high-value buyer messages on a Saturday evening, the operator should get a
tap on their personal WhatsApp — not have to discover it Monday morning.

Trigger
-------
Fires when a draft is queued AND the inbound classifier read it as one of:
  - urgency ∈ {hot, on_fire}                  (genuine intent to move now)
  - stage   ∈ {negotiating, closing}          (deal is at the table)
  - sentiment == angry OR stage == complaint  (P0 — owner attention regardless)

Throttle
--------
Max 1 alert per (client_id, contact_phone) per hour. We're nudging the owner,
not spamming them.

Channel
-------
WhatsApp to client.owner_phone via Unipile (the platform default — NOT the
client's own line, since this is owner-facing internal comms).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Collection ───────────────────────────────────────────────────────────────

def _db():
    return get_db()


def get_alerts_col():
    return _db()["sales_alerts_sent"]


def ensure_sales_alert_indexes() -> None:
    col = get_alerts_col()
    col.create_index([("client_id", ASCENDING), ("contact_phone", ASCENDING), ("ts", DESCENDING)])
    col.create_index([("ts", DESCENDING)])


# ─── Trigger logic ────────────────────────────────────────────────────────────

HOT_URGENCIES = {"hot", "on_fire"}
HOT_STAGES = {"negotiating", "closing"}


def should_alert(classification: Optional[dict]) -> tuple[bool, str]:
    """Decide whether a draft warrants an owner ping. Returns (yes/no, reason)."""
    if not classification:
        return False, "no classification"
    c = classification
    sentiment = (c.get("sentiment") or "").lower()
    stage = (c.get("stage") or "").lower()
    urgency = (c.get("urgency") or "").lower()
    confidence = float(c.get("confidence") or 0)

    if sentiment == "angry":
        return True, "customer is angry — needs human"
    if stage == "complaint":
        return True, "complaint — needs human"
    if urgency == "on_fire" and confidence >= 0.65:
        return True, "buyer is on fire — strike now"
    if urgency == "hot" and stage in HOT_STAGES and confidence >= 0.6:
        return True, f"hot lead in {stage} stage"
    if stage == "closing" and confidence >= 0.7:
        return True, "lead is at closing — owner should jump in"
    return False, "no trigger"


# ─── Throttle ─────────────────────────────────────────────────────────────────

def _recently_alerted(client_id: str, contact_phone: str, within_minutes: int = 60) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    return bool(
        get_alerts_col().find_one(
            {"client_id": client_id, "contact_phone": contact_phone,
             "ts": {"$gte": cutoff}},
            {"_id": 1},
        )
    )


# ─── Alert send ───────────────────────────────────────────────────────────────

def _format_alert(
    *,
    agent_name: str,
    contact_name: str,
    contact_phone: str,
    inbound_excerpt: Optional[str],
    suggested_reply: str,
    reason: str,
    portal_link: Optional[str],
) -> str:
    inbound_line = ""
    if inbound_excerpt:
        snip = inbound_excerpt.strip().replace("\n", " ")
        if len(snip) > 180:
            snip = snip[:180] + "…"
        inbound_line = f"\nThey said: \"{snip}\""
    reply_snip = (suggested_reply or "").strip().replace("\n", " ")
    if len(reply_snip) > 220:
        reply_snip = reply_snip[:220] + "…"
    link_line = f"\n\nOpen queue: {portal_link}" if portal_link else ""
    return (
        f"🔥 Hot lead from *{contact_name}* ({contact_phone}).\n"
        f"Reason: {reason}.{inbound_line}\n\n"
        f"{agent_name}'s draft (waiting your tap):\n"
        f"\"{reply_snip}\"{link_line}"
    )


async def _send_to_owner(owner_phone: str, text: str) -> bool:
    """Send via Unipile platform default — owner-facing, not client's own line."""
    try:
        from tools.outreach import send_whatsapp_for_client
        await send_whatsapp_for_client(phone=owner_phone, message=text)
        return True
    except Exception as e:
        log.warning("sales_alert_send_failed", error=str(e))
        return False


async def alert_owner_about_draft(
    *,
    client_id: str,
    contact_phone: str,
    contact_name: str,
    classification: dict,
    suggested_reply: str,
    inbound_excerpt: Optional[str] = None,
    approval_id: Optional[str] = None,
) -> bool:
    """Called immediately after a draft is queued. Decides + sends. Idempotent
    via throttle. Returns True if an alert was sent."""
    should, reason = should_alert(classification)
    if not should:
        return False

    # Client config check
    db = _db()
    try:
        client = db["clients"].find_one(
            {"_id": ObjectId(client_id)},
            {"owner_phone": 1, "agent_name": 1, "alerts_enabled": 1, "portal_token": 1, "name": 1},
        )
    except Exception:
        return False
    if not client:
        return False
    # Allow opt-out via client.alerts_enabled = False (default ON).
    if client.get("alerts_enabled") is False:
        return False
    owner_phone = client.get("owner_phone")
    if not owner_phone:
        log.info("sales_alert_no_owner_phone", client_id=client_id)
        return False

    # Throttle
    if _recently_alerted(client_id, contact_phone):
        log.info("sales_alert_throttled", client_id=client_id, contact=contact_phone)
        return False

    agent_name = client.get("agent_name") or "EYO"
    portal_link = None
    if client.get("portal_token"):
        portal_link = f"https://www.reachng.ng/portal/{client['portal_token']}"

    body = _format_alert(
        agent_name=agent_name,
        contact_name=contact_name or "your contact",
        contact_phone=contact_phone,
        inbound_excerpt=inbound_excerpt,
        suggested_reply=suggested_reply,
        reason=reason,
        portal_link=portal_link,
    )

    sent = await _send_to_owner(owner_phone, body)
    if sent:
        try:
            get_alerts_col().insert_one({
                "client_id":     client_id,
                "client_name":   client.get("name"),
                "contact_phone": contact_phone,
                "contact_name":  contact_name,
                "approval_id":   approval_id,
                "reason":        reason,
                "ts":            datetime.now(timezone.utc),
            })
        except Exception as e:
            log.warning("sales_alert_persist_failed", error=str(e))
        log.info("sales_alert_sent", client=client.get("name"), contact=contact_name, reason=reason)
    return sent
