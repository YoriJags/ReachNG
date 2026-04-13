"""
Outreach delivery — Meta Cloud API for WhatsApp, Unipile for email (fallback: Gmail SMTP).
Reply polling: Meta pushes replies via webhook; email replies polled via Unipile or Gmail IMAP.
"""
import asyncio
import imaplib
import email as email_lib
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings
import httpx
import structlog

log = structlog.get_logger()


# ─── WhatsApp — Meta Cloud API ────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_whatsapp(phone: str, message: str, account_id: Optional[str] = None) -> dict:
    """
    Send a WhatsApp message via Meta Cloud API.
    phone: E.164 format — +2348012345678
    account_id: ignored (kept for call-site compatibility — Meta uses env vars)
    """
    settings = get_settings()
    phone_number_id = settings.meta_phone_number_id
    access_token    = settings.meta_access_token

    if not phone_number_id or not access_token:
        log.error("meta_credentials_missing")
        return {"success": False, "error": "META credentials not configured"}

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code == 400:
            body = resp.json()
            log.warning("meta_whatsapp_bad_request", phone=phone, detail=body)
            return {"success": False, "error": "bad_request", "detail": body}
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("messages", [{}])[0].get("id")
        log.info("whatsapp_sent", phone=phone, message_id=msg_id)
        return {"success": True, "message_id": msg_id}


async def send_whatsapp_meta(
    phone: str,
    message: str,
    phone_number_id: str,
    access_token: str,
) -> dict:
    """Send via a specific client's Meta credentials (agency mode)."""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code == 400:
            return {"success": False, "error": "bad_request", "detail": resp.json()}
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
    Route WhatsApp through the right Meta credentials.
    If client has their own Meta credentials, use those.
    Otherwise fall back to the default Meta account (env vars).
    """
    if client_doc and client_doc.get("whatsapp_provider") == "meta":
        phone_number_id = client_doc.get("meta_phone_number_id")
        access_token    = client_doc.get("meta_access_token")
        if phone_number_id and access_token:
            return await send_whatsapp_meta(phone, message, phone_number_id, access_token)
        log.warning("client_meta_credentials_missing", client=client_doc.get("name"))

    # Default: ReachNG's own Meta account
    return await send_whatsapp(phone, message)


# ─── Email — Unipile (primary) / Gmail SMTP (fallback) ───────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
    account_id: Optional[str] = None,  # kept for call-site compatibility
) -> dict:
    """
    Send email via Unipile if configured, otherwise fall back to Gmail SMTP.
    Unipile requires: UNIPILE_DSN + UNIPILE_API_KEY + UNIPILE_EMAIL_ACCOUNT_ID.
    Gmail fallback requires: GMAIL_ADDRESS + GMAIL_APP_PASSWORD.
    """
    settings = get_settings()

    # ── Unipile path ──────────────────────────────────────────────────────────
    dsn        = settings.unipile_dsn
    api_key    = settings.unipile_api_key
    email_acct = settings.unipile_email_account_id

    if dsn and api_key and email_acct:
        base_url = f"https://{dsn}"
        payload: dict = {
            "account_id": email_acct,
            "to":         [{"identifier": to_email}],
            "subject":    subject,
            "body":       body,
        }
        if reply_to:
            payload["reply_to"] = [{"identifier": reply_to}]
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{base_url}/api/v1/emails",
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                msg_id = data.get("id") or data.get("email_id", "unipile-email")
                log.info("email_sent_unipile", to=to_email, message_id=msg_id)
                return {"success": True, "message_id": msg_id, "provider": "unipile"}
        except Exception as e:
            log.warning("unipile_email_failed_falling_back", to=to_email, error=str(e))
            # fall through to Gmail

    # ── Gmail SMTP fallback ───────────────────────────────────────────────────
    gmail_address = settings.gmail_address
    app_password  = settings.gmail_app_password

    if not gmail_address or not app_password:
        log.error("email_credentials_missing")
        return {"success": False, "error": "No email provider configured (Unipile or Gmail)"}

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_address
        msg["To"]      = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body, "plain"))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, to_email, msg.as_string())

    try:
        await asyncio.to_thread(_send_sync)
        log.info("email_sent_gmail", to=to_email, subject=subject)
        return {"success": True, "message_id": f"gmail-{to_email}-{subject[:20]}", "provider": "gmail"}
    except Exception as e:
        log.error("email_send_failed", to=to_email, error=str(e))
        return {"success": False, "error": str(e)}


# ─── Reply polling ────────────────────────────────────────────────────────────

async def check_whatsapp_replies() -> list[dict]:
    """
    Meta pushes WhatsApp replies via webhook to /api/v1/webhooks.
    Polling is not needed — return empty list and let the webhook handler do the work.
    """
    return []


async def check_email_replies() -> list[dict]:
    """
    Poll email replies via Unipile (primary) or Gmail IMAP (fallback).
    Returns message dicts compatible with reply_router._route_reply.
    """
    settings = get_settings()

    # ── Unipile path ──────────────────────────────────────────────────────────
    dsn        = settings.unipile_dsn
    api_key    = settings.unipile_api_key
    email_acct = settings.unipile_email_account_id

    if dsn and api_key and email_acct:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://{dsn}/api/v1/emails",
                    headers={"X-API-KEY": api_key},
                    params={"account_id": email_acct, "limit": 50, "folder": "INBOX"},
                )
                resp.raise_for_status()
                items = resp.json().get("items", [])
                messages = []
                for item in items:
                    messages.append({
                        "id": item.get("id", ""),
                        "from": {"identifier": item.get("from_attendee", {}).get("identifier", "")},
                        "subject": item.get("subject", ""),
                        "body": item.get("body", "")[:2000],
                    })
                log.info("email_replies_polled_unipile", count=len(messages))
                return messages
        except Exception as e:
            log.warning("unipile_email_poll_failed_falling_back", error=str(e))
            # fall through to Gmail IMAP

    # ── Gmail IMAP fallback ───────────────────────────────────────────────────
    gmail_address = settings.gmail_address
    app_password  = settings.gmail_app_password

    if not gmail_address or not app_password:
        return []

    def _poll_imap() -> list[dict]:
        import re
        messages = []
        try:
            with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
                mail.login(gmail_address, app_password)
                mail.select("inbox")
                _, data = mail.search(None, "UNSEEN")
                uids = data[0].split()
                for uid in uids[-50:]:
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    parsed = email_lib.message_from_bytes(raw)
                    from_addr = parsed.get("From", "")
                    match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', from_addr)
                    sender = match.group(0) if match else from_addr
                    body = ""
                    if parsed.is_multipart():
                        for part in parsed.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = parsed.get_payload(decode=True).decode("utf-8", errors="ignore")
                    messages.append({
                        "id": uid.decode(),
                        "from": {"identifier": sender},
                        "subject": parsed.get("Subject", ""),
                        "body": body[:2000],
                    })
        except Exception as e:
            log.error("gmail_imap_poll_failed", error=str(e))
        return messages

    return await asyncio.to_thread(_poll_imap)


# ─── Instagram DM — Unipile ──────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_instagram_dm(recipient_id: str, message: str) -> dict:
    """
    Send an Instagram DM via Unipile.
    recipient_id: Instagram user ID (not username).
    Requires: UNIPILE_DSN + UNIPILE_API_KEY + UNIPILE_INSTAGRAM_ACCOUNT_ID.
    """
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    ig_acct = settings.unipile_instagram_account_id

    if not (dsn and api_key and ig_acct):
        log.error("unipile_instagram_credentials_missing")
        return {"success": False, "error": "Unipile Instagram not configured"}

    payload = {
        "account_id":    ig_acct,
        "attendees_ids": [recipient_id],
        "text":          message,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"https://{dsn}/api/v1/chats",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data   = resp.json()
            msg_id = data.get("id", "ig-dm")
            log.info("instagram_dm_sent", recipient=recipient_id, message_id=msg_id)
            return {"success": True, "message_id": msg_id, "provider": "unipile_instagram"}
    except Exception as e:
        log.error("instagram_dm_failed", recipient=recipient_id, error=str(e))
        return {"success": False, "error": str(e)}


# ─── LinkedIn Message — Unipile ───────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def send_linkedin_message(recipient_id: str, message: str) -> dict:
    """
    Send a LinkedIn message via Unipile.
    recipient_id: LinkedIn member URN or profile ID.
    Requires: UNIPILE_DSN + UNIPILE_API_KEY + UNIPILE_LINKEDIN_ACCOUNT_ID.
    """
    settings = get_settings()
    dsn      = settings.unipile_dsn
    api_key  = settings.unipile_api_key
    li_acct  = getattr(settings, "unipile_linkedin_account_id", None)

    if not (dsn and api_key and li_acct):
        log.error("unipile_linkedin_credentials_missing")
        return {"success": False, "error": "Unipile LinkedIn not configured"}

    payload = {
        "account_id":    li_acct,
        "attendees_ids": [recipient_id],
        "text":          message,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"https://{dsn}/api/v1/chats",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data   = resp.json()
            msg_id = data.get("id", "li-msg")
            log.info("linkedin_message_sent", recipient=recipient_id, message_id=msg_id)
            return {"success": True, "message_id": msg_id, "provider": "unipile_linkedin"}
    except Exception as e:
        log.error("linkedin_message_failed", recipient=recipient_id, error=str(e))
        return {"success": False, "error": str(e)}


# ─── Legacy stubs — keep call sites working ──────────────────────────────────

async def get_recent_replies(account_id: str, limit: int = 50) -> list[dict]:
    """Deprecated — Meta uses webhooks, Gmail uses IMAP. Returns empty list."""
    return []
