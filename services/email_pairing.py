"""Per-client EMAIL pairing via Unipile hosted-auth (Gmail / Outlook).

Mirrors services/whatsapp_pairing exactly — the SAME Unipile hosted-auth link +
the SAME `/api/v1/webhooks/unipile/account` callback — but it requests email
providers and tags the channel in `name` (`client:<id>|chan:email`) so the shared
account webhook routes the result onto `email_account_id`, not the WhatsApp slot.

This is the foundation of EYO-on-email: once a client's mailbox is paired, the
same brain that works WhatsApp can read + reply to their customer emails.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings

log = structlog.get_logger()

# What we ask Unipile's hosted page to offer for an email connect.
EMAIL_PROVIDERS = ["GOOGLE", "OUTLOOK"]
# Account `type` values Unipile reports for mailboxes (used as a fallback route).
_EMAIL_TYPES = {"GOOGLE", "OUTLOOK", "MAIL", "IMAP", "GMAIL",
                "GOOGLE_OAUTH", "OUTLOOK_OAUTH", "EXCHANGE"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
async def start_email_hosted_auth(*, client_id: str, app_base_url: str,
                                  expires_minutes: int = 30) -> dict:
    """Request an email hosted-auth link from Unipile. Returns {url, id, expires_on}."""
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    if not (dsn and api_key):
        raise RuntimeError("Unipile not configured (UNIPILE_DSN + UNIPILE_API_KEY required)")

    expires_on = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")
    base = f"https://{dsn}"
    payload = {
        "type":                 "create",
        "providers":            EMAIL_PROVIDERS,
        "api_url":              base,
        "expiresOn":            expires_on,
        # `chan:email` tells the shared webhook to store this as the email account.
        "name":                 f"client:{client_id}|chan:email",
        "success_redirect_url": f"{app_base_url}/portal/email/connected",
        "failure_redirect_url": f"{app_base_url}/portal/email/failed",
        "notify_url":           f"{app_base_url}/api/v1/webhooks/unipile/account",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{base}/api/v1/hosted/accounts/link",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    log.info("unipile_email_hosted_auth_started", client_id=client_id, link_id=data.get("id"))
    return {"url": data.get("url"), "id": data.get("id"), "expires_on": expires_on}


def is_email_account_type(acc_type: str | None) -> bool:
    """True when Unipile's account `type` looks like a mailbox (route fallback)."""
    return (acc_type or "").upper() in _EMAIL_TYPES


def parse_channel_from_name(name: str | None) -> str:
    """'email' when the pairing was started as email, else 'whatsapp'. The echoed
    `name` carries `|chan:email` for email connects (WhatsApp omits it)."""
    if name and "|chan:email" in name:
        return "email"
    return "whatsapp"
