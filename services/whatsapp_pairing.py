"""
WhatsApp pairing via Unipile hosted-auth.

Flow:
  1. Client portal POSTs to /api/v1/portal/{token}/whatsapp/connect/start
  2. We call Unipile → POST /api/v1/hosted/accounts/link with type=WHATSAPP
     Unipile returns {url, id}. `url` is a hosted page that renders a QR
     the client scans with WhatsApp → Linked Devices.
  3. Client scans, completes auth. Unipile fires a webhook to our
     `notify_url` with {account_id, status, name}.
  4. Webhook handler stores `whatsapp_account_id` on the matching client doc.
  5. Portal polls /status which checks the client doc + Unipile account
     state to flip the UI.

Why hosted-auth (not raw QR fetch): Unipile's hosted page handles QR
refresh, re-scans, expired QRs, mobile rendering. We avoid rebuilding that.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings

log = structlog.get_logger()


# ─── Public ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
async def start_hosted_auth(*, client_id: str, app_base_url: str,
                             expires_minutes: int = 30) -> dict:
    """Request a hosted-auth link from Unipile. Returns {url, id}.

    `client_id` is passed in `name` so the webhook can route the result back
    to the right client. Unipile hosted-auth URL is short-lived (default 1
    hour, we shorten to 30 min for security).

    Raises if Unipile is misconfigured or the call fails after retries.
    """
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    if not (dsn and api_key):
        raise RuntimeError("Unipile not configured (UNIPILE_DSN + UNIPILE_API_KEY required)")

    expires_on = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    base = f"https://{dsn}"
    payload = {
        "type":                  "create",
        "providers":             ["WHATSAPP"],
        "api_url":               base,
        "expiresOn":             expires_on,
        "name":                  f"client:{client_id}",  # routes back via webhook.name
        "success_redirect_url":  f"{app_base_url}/portal/whatsapp/connected",
        "failure_redirect_url":  f"{app_base_url}/portal/whatsapp/failed",
        "notify_url":            f"{app_base_url}/api/v1/webhooks/unipile/account",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{base}/api/v1/hosted/accounts/link",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    log.info("unipile_hosted_auth_started", client_id=client_id, link_id=data.get("id"))
    return {
        "url":         data.get("url"),
        "id":          data.get("id"),
        "expires_on":  expires_on,
    }


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def get_account_status(account_id: str) -> Optional[dict]:
    """Fetch an account's current state from Unipile.

    Returns the raw account dict on success, None if not found.
    Key fields: `id`, `type` (WHATSAPP), `sources[].status` (OK | CREDENTIALS | ...)
    """
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    if not (dsn and api_key):
        raise RuntimeError("Unipile not configured")

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            f"https://{dsn}/api/v1/accounts/{account_id}",
            headers={"X-API-KEY": api_key},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


def is_account_healthy(account_doc: dict) -> bool:
    """True if every WhatsApp source on the account is OK / connected.

    Unipile shape: {sources: [{status: "OK"|"CREDENTIALS"|"DISCONNECTED"|...}]}
    """
    sources = account_doc.get("sources") or []
    if not sources:
        return False
    return all((s.get("status") or "").upper() == "OK" for s in sources)


# ─── Helpers ────────────────────────────────────────────────────────────────

def parse_client_id_from_name(name: Optional[str]) -> Optional[str]:
    """Webhook payload echoes back the `name` we sent. We use `client:{id}`
    so this just splits it back out."""
    if not name or not name.startswith("client:"):
        return None
    return name.split(":", 1)[1].strip() or None
