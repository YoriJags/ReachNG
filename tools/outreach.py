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


def _pick_active_meta_account(client_doc: dict) -> Optional[dict]:
    """Multi-line failover (WhatsApp ban defence).

    Schema: `client_doc.whatsapp_accounts` is an ordered list of dicts
        [{"label": "primary", "meta_phone_number_id": ..., "meta_access_token": ...,
          "health": "OK"|"NOT_OK", "primary": True/False}, ...]
    We pick the first entry with health == "OK" (or unset), preferring the one
    flagged `primary`. Falls back to legacy single-field fields when no list.
    """
    accounts = client_doc.get("whatsapp_accounts") or []
    if accounts:
        ordered = sorted(accounts, key=lambda a: (not a.get("primary"), 0))
        for a in ordered:
            if (a.get("health") or "OK") == "OK" and a.get("meta_phone_number_id") and a.get("meta_access_token"):
                return a
        # All marked NOT_OK — try any with creds as last resort
        for a in ordered:
            if a.get("meta_phone_number_id") and a.get("meta_access_token"):
                log.warning("all_whatsapp_lines_unhealthy_using_last_resort",
                            client=client_doc.get("name"), label=a.get("label"))
                return a
        return None
    # Legacy single-line
    if client_doc.get("meta_phone_number_id") and client_doc.get("meta_access_token"):
        return {"meta_phone_number_id": client_doc["meta_phone_number_id"],
                "meta_access_token":    client_doc["meta_access_token"],
                "label":                "legacy"}
    return None


async def send_whatsapp_for_client(
    phone: str,
    message: str,
    client_doc: Optional[dict] = None,
) -> dict:
    """
    Route WhatsApp through the right Meta credentials with failover.

    If the client has `whatsapp_accounts: [...]` configured, picks the
    healthy primary first; on send failure, marks that account NOT_OK and
    retries on the next available line. Single-line clients fall through
    unchanged.
    """
    if client_doc and client_doc.get("whatsapp_provider") == "meta":
        accounts = client_doc.get("whatsapp_accounts") or []
        if accounts:
            # Try each healthy account, failing over on send error
            last_error = None
            ordered = sorted(accounts, key=lambda a: (not a.get("primary"), 0))
            for a in ordered:
                if (a.get("health") or "OK") != "OK":
                    continue
                pn = a.get("meta_phone_number_id")
                tok = a.get("meta_access_token")
                if not (pn and tok):
                    continue
                try:
                    result = await send_whatsapp_meta(phone, message, pn, tok)
                    if result.get("success"):
                        return result
                    last_error = result
                except Exception as e:
                    last_error = {"success": False, "error": str(e), "label": a.get("label")}
                # Mark this line as unhealthy and try the next
                try:
                    from database import get_db
                    get_db()["clients"].update_one(
                        {"_id": client_doc["_id"], "whatsapp_accounts.label": a.get("label")},
                        {"$set": {"whatsapp_accounts.$.health": "NOT_OK",
                                  "whatsapp_accounts.$.last_failure_at":
                                      __import__("datetime").datetime.now(
                                          __import__("datetime").timezone.utc)}},
                    )
                except Exception:
                    pass
                log.warning("whatsapp_line_failover",
                            client=client_doc.get("name"),
                            failed_label=a.get("label"))
            if last_error:
                log.error("all_whatsapp_lines_failed",
                          client=client_doc.get("name"), last=last_error)
                return last_error or {"success": False, "error": "all lines failed"}
        # No accounts list → try the legacy single-line credentials
        pick = _pick_active_meta_account(client_doc)
        if pick:
            return await send_whatsapp_meta(phone, message,
                                             pick["meta_phone_number_id"],
                                             pick["meta_access_token"])
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
    force_smtp: bool = False,
    html: Optional[str] = None,
) -> dict:
    """
    Send email via Unipile if configured, otherwise fall back to Gmail SMTP.
    Unipile requires: UNIPILE_DSN + UNIPILE_API_KEY + UNIPILE_EMAIL_ACCOUNT_ID.
    Gmail fallback requires: GMAIL_ADDRESS + GMAIL_APP_PASSWORD.

    force_smtp=True bypasses Unipile entirely — use for transactional sends
    that must originate from hello@reachng.ng (waitlist, Paystack welcome
    when no client mailbox exists yet, etc.) rather than a client's connected
    Unipile account.
    """
    settings = get_settings()

    # ── Resend path (preferred for transactional — HTTPS, no SMTP egress) ────
    resend_key = settings.resend_api_key
    if resend_key and (force_smtp or not (settings.unipile_dsn and settings.unipile_api_key and settings.unipile_email_account_id)):
        try:
            payload: dict = {
                "from":    settings.resend_from_email,
                "to":      [to_email],
                "subject": subject,
                "text":    body,
            }
            if html:
                payload["html"] = html
            if reply_to:
                payload["reply_to"] = reply_to
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                msg_id = data.get("id", "resend-email")
                log.info("email_sent_resend", to=to_email, message_id=msg_id)
                return {"success": True, "message_id": msg_id, "provider": "resend"}
        except Exception as e:
            log.warning("resend_email_failed_falling_back", to=to_email, error=str(e))
            # fall through to Unipile or Gmail

    # ── Unipile path ──────────────────────────────────────────────────────────
    dsn        = settings.unipile_dsn
    api_key    = settings.unipile_api_key
    email_acct = settings.unipile_email_account_id

    if not force_smtp and dsn and api_key and email_acct:
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

    smtp_host = settings.smtp_host
    smtp_port = settings.smtp_port
    use_ssl   = settings.smtp_use_ssl

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_address
        msg["To"]      = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body, "plain"))
        context = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(gmail_address, app_password)
                server.sendmail(gmail_address, to_email, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
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
        imap_host = settings.imap_host
        imap_port = settings.imap_port
        try:
            with imaplib.IMAP4_SSL(imap_host, imap_port) as mail:
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
            log.error("imap_poll_failed", host=imap_host, error=str(e))
        return messages

    return await asyncio.to_thread(_poll_imap)


# ─── Legacy stubs — keep call sites working ──────────────────────────────────

async def get_recent_replies(account_id: str, limit: int = 50) -> list[dict]:
    """Deprecated — Meta uses webhooks, Gmail uses IMAP. Returns empty list."""
    return []
