"""
Unipile outreach tool — sends WhatsApp messages and emails.
Unipile is a unified messaging API: one integration covers both channels.
Docs: https://developer.unipile.com
"""
import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings
import structlog

log = structlog.get_logger()


def _base_url() -> str:
    settings = get_settings()
    return f"https://{settings.unipile_dsn}"


def _headers() -> dict:
    settings = get_settings()
    return {
        "X-API-KEY": settings.unipile_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── WhatsApp ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_whatsapp(phone: str, message: str, account_id: Optional[str] = None) -> dict:
    """
    Send a WhatsApp message to a phone number.
    Phone must be in E.164 format: +2348012345678
    account_id: use client's own Unipile account if provided, else fall back to default.
    Returns Unipile response with message_id.
    """
    settings = get_settings()
    wa_account = account_id or settings.unipile_whatsapp_account_id

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{_base_url()}/api/v1/chats",
            headers=_headers(),
            json={
                "account_id": wa_account,
                "attendees_ids": [phone],
                "text": message,
            },
        )

        if resp.status_code == 400:
            body = resp.json()
            # Unipile returns 400 for invalid/unreachable numbers
            log.warning("whatsapp_invalid_number", phone=phone, detail=body)
            return {"success": False, "error": "invalid_number", "detail": body}

        resp.raise_for_status()
        data = resp.json()
        log.info("whatsapp_sent", phone=phone, chat_id=data.get("id"))
        return {"success": True, "chat_id": data.get("id")}


# ─── Meta Cloud API WhatsApp ──────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_whatsapp_meta(
    phone: str,
    message: str,
    phone_number_id: str,
    access_token: str,
) -> dict:
    """
    Send a WhatsApp message via Meta Cloud API (official Business API).
    Client connects their own WhatsApp Business number — zero cost per account.
    Phone must be E.164 format: +2348012345678
    phone_number_id: from Meta Business Manager / WhatsApp Business API setup
    access_token: permanent system user token from Meta Business Manager
    """
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 400:
            body = resp.json()
            log.warning("meta_whatsapp_bad_request", phone=phone, detail=body)
            return {"success": False, "error": "bad_request", "detail": body}
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("messages", [{}])[0].get("id")
        log.info("meta_whatsapp_sent", phone=phone, message_id=msg_id)
        return {"success": True, "message_id": msg_id}


async def send_whatsapp_for_client(
    phone: str,
    message: str,
    client_doc: Optional[dict] = None,
) -> dict:
    """
    Route WhatsApp send through the right provider based on client config.
    - client.whatsapp_provider == 'meta'    → Meta Cloud API (client's own number, no Unipile cost)
    - client.whatsapp_provider == 'unipile' → Unipile (default, uses client's account_id)
    - no client_doc                         → Unipile default account (your own number)
    """
    if client_doc and client_doc.get("whatsapp_provider") == "meta":
        phone_number_id = client_doc.get("meta_phone_number_id")
        access_token    = client_doc.get("meta_access_token")
        if not phone_number_id or not access_token:
            log.warning("meta_credentials_missing", client=client_doc.get("name"))
            # Fallback to Unipile
        else:
            return await send_whatsapp_meta(phone, message, phone_number_id, access_token)

    # Unipile path
    account_id = client_doc.get("whatsapp_account_id") if client_doc else None
    return await send_whatsapp(phone, message, account_id=account_id)


# ─── Email ────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
    account_id: Optional[str] = None,
) -> dict:
    """
    Send an email via Unipile.
    account_id: use client's own Unipile account if provided, else fall back to default.
    Returns Unipile response with message_id.
    """
    settings = get_settings()
    email_account = account_id or settings.unipile_email_account_id

    payload = {
        "account_id": email_account,
        "to": [{"identifier": to_email}],
        "subject": subject,
        "body": body,
    }
    if reply_to:
        payload["reply_to"] = [{"identifier": reply_to}]

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{_base_url()}/api/v1/emails",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        log.info("email_sent", to=to_email, subject=subject, message_id=data.get("id"))
        return {"success": True, "message_id": data.get("id")}


# ─── Response polling ─────────────────────────────────────────────────────────

async def get_recent_replies(account_id: str, limit: int = 50) -> list[dict]:
    """
    Poll Unipile for recent messages received across all chats.
    Used by the follow-up scheduler to detect replies.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_base_url()}/api/v1/messages",
            headers=_headers(),
            params={
                "account_id": account_id,
                "limit": limit,
                "role": "RECIPIENT",   # Messages sent TO us
            },
        )
        resp.raise_for_status()
        return resp.json().get("items", [])


async def check_whatsapp_replies() -> list[dict]:
    settings = get_settings()
    return await get_recent_replies(settings.unipile_whatsapp_account_id)


async def check_email_replies() -> list[dict]:
    settings = get_settings()
    return await get_recent_replies(settings.unipile_email_account_id)
