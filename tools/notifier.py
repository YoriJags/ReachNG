"""
Owner notifications — alerts you directly when a reply comes in.
Supports WhatsApp (via Unipile) and Slack (via webhook).
Configure OWNER_WHATSAPP and/or SLACK_WEBHOOK_URL in .env to enable.
"""
import httpx
import structlog
from config import get_settings

log = structlog.get_logger()

INTENT_EMOJI = {
    "interested": "🔥",
    "not_now":    "⏳",
    "opted_out":  "🚫",
    "referral":   "🤝",
    "question":   "❓",
    "unknown":    "💬",
}


def _build_alert(
    contact_name: str,
    vertical: str,
    channel: str,
    reply_text: str,
    intent: str,
    urgency: str,
    summary: str,
) -> str:
    emoji = INTENT_EMOJI.get(intent, "💬")
    urgency_tag = "🚨 HIGH" if urgency == "high" else ("⚡ MED" if urgency == "medium" else "")
    tag = f" {urgency_tag}" if urgency_tag else ""

    return (
        f"{emoji} *ReachNG Reply*{tag}\n\n"
        f"*From:* {contact_name}\n"
        f"*Vertical:* {vertical.replace('_', ' ').title()}\n"
        f"*Channel:* {channel.title()}\n"
        f"*Intent:* {intent.replace('_', ' ').title()}\n\n"
        f"*Summary:* {summary}\n\n"
        f"*Their message:*\n_{reply_text[:300]}_"
    )


async def notify_whatsapp(
    contact_name: str,
    vertical: str,
    channel: str,
    reply_text: str,
    intent: str,
    urgency: str,
    summary: str,
) -> bool:
    """Send a WhatsApp alert to the owner's personal number via Unipile."""
    settings = get_settings()
    owner_phone = getattr(settings, "owner_whatsapp", None)
    if not owner_phone:
        return False

    message = _build_alert(contact_name, vertical, channel, reply_text, intent, urgency, summary)

    try:
        base_url = f"https://{settings.unipile_dsn}"
        headers = {
            "X-API-KEY": settings.unipile_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/api/v1/chats",
                headers=headers,
                json={
                    "account_id": settings.unipile_whatsapp_account_id,
                    "attendees_ids": [owner_phone],
                    "text": message,
                },
            )
            resp.raise_for_status()
            log.info("owner_whatsapp_alert_sent", contact=contact_name, intent=intent)
            return True
    except Exception as e:
        log.error("owner_whatsapp_alert_failed", error=str(e))
        return False


async def notify_slack(
    contact_name: str,
    vertical: str,
    channel: str,
    reply_text: str,
    intent: str,
    urgency: str,
    summary: str,
) -> bool:
    """Post a Slack alert via incoming webhook."""
    settings = get_settings()
    webhook_url = getattr(settings, "slack_webhook_url", None)
    if not webhook_url:
        return False

    emoji = INTENT_EMOJI.get(intent, "💬")
    color = "#00C851" if intent == "interested" else ("#FF4444" if intent == "opted_out" else "#FFBB33")

    payload = {
        "attachments": [{
            "color": color,
            "title": f"{emoji} ReachNG — {intent.replace('_', ' ').title()} Reply",
            "fields": [
                {"title": "Contact", "value": contact_name, "short": True},
                {"title": "Vertical", "value": vertical.replace("_", " ").title(), "short": True},
                {"title": "Channel", "value": channel.title(), "short": True},
                {"title": "Urgency", "value": urgency.title(), "short": True},
                {"title": "Summary", "value": summary, "short": False},
                {"title": "Their message", "value": reply_text[:300], "short": False},
            ],
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            log.info("slack_alert_sent", contact=contact_name, intent=intent)
            return True
    except Exception as e:
        log.error("slack_alert_failed", error=str(e))
        return False


async def notify_owner(
    contact_name: str,
    vertical: str,
    channel: str,
    reply_text: str,
    intent: str,
    urgency: str,
    summary: str,
):
    """Fire both notification channels concurrently."""
    import asyncio
    await asyncio.gather(
        notify_whatsapp(contact_name, vertical, channel, reply_text, intent, urgency, summary),
        notify_slack(contact_name, vertical, channel, reply_text, intent, urgency, summary),
        return_exceptions=True,
    )
