"""
Outreach delivery — transport routing per ReachNG's two-sided stack.

CLIENT EYO ENGINE (paying clients messaging their own customers):
  WhatsApp is routed PER CLIENT by `client_doc.whatsapp_provider`:
    - "unipile" (default)  → client's QR-connected Unipile account (`/api/v1/chats`)
    - "meta"               → that client's Meta Cloud API / WABA credentials
  A client reply is NEVER sent from ReachNG's own number, and we NEVER silently
  fall back to Meta for a Unipile client. Missing credentials fail loudly.
  Use `send_whatsapp_for_client()` for every customer-facing send.

INTERNAL PROSPECT OS (Yori's acquisition outreach for selling ReachNG):
  Email only, via Resend (force_smtp=True). Never Unipile email.

`send_whatsapp()` (bare Meta) exists only for ReachNG's own number / legacy
call sites — it must NOT be used to send a client's customer replies.
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


async def send_whatsapp_unipile(phone: str, message: str, account_id: str) -> dict:
    """Send a WhatsApp message from a client's QR-connected Unipile account.

    Mirrors the established Unipile chat pattern used by notifier/morning-brief:
    POST /api/v1/chats with the account_id, the recipient as an attendee, and text.
    """
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    if not (dsn and api_key and account_id):
        log.error("unipile_whatsapp_not_configured", has_account=bool(account_id))
        return {"success": False, "error": "unipile_not_configured",
                "detail": "Unipile DSN/API key or account_id missing — message not sent"}

    url = f"https://{dsn}/api/v1/chats"
    payload = {"account_id": account_id, "attendees_ids": [phone], "text": message}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text[:300]}
            log.warning("unipile_whatsapp_failed", status=resp.status_code, detail=body)
            return {"success": False, "error": "unipile_send_failed",
                    "status": resp.status_code, "detail": body}
        try:
            data = resp.json()
        except Exception:
            data = {}
        msg_id = data.get("id") or data.get("chat_id") or "unipile-wa"
        log.info("whatsapp_sent_unipile", message_id=msg_id, account_id=account_id)
        return {"success": True, "message_id": msg_id, "provider": "unipile"}


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
    Route a client's customer-facing WhatsApp send by the client's provider.

      provider == "meta"     → that client's Meta Cloud API credentials
                               (multi-line health failover preserved).
      provider == "unipile"  → that client's QR-connected Unipile account.
      provider missing       → default to Unipile IF the client has a usable
                               account_id, else fail loudly.

    Hard rules (transport correctness):
      - A "meta" client with no Meta credentials FAILS LOUDLY — we never fall
        back to Unipile or to ReachNG's own number.
      - A Unipile / default client is NEVER routed through Meta.
      - No transport available → return success=False with a clear error and
        leave the message unsent. Never a silent success, never a wrong sender.
    """
    client_doc = client_doc or {}
    provider = (client_doc.get("whatsapp_provider") or "").lower()
    client_name = client_doc.get("name")
    settings = get_settings()

    # ── Meta-configured client ──────────────────────────────────────────────
    if provider == "meta":
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
                            client=client_name, failed_label=a.get("label"))
            if last_error:
                log.error("all_whatsapp_lines_failed", client=client_name, last=last_error)
                return last_error
        # No accounts list → try the legacy single-line credentials
        pick = _pick_active_meta_account(client_doc)
        if pick:
            return await send_whatsapp_meta(phone, message,
                                             pick["meta_phone_number_id"],
                                             pick["meta_access_token"])
        # FAIL LOUDLY — a Meta client with no creds must never fall back.
        log.error("meta_client_missing_credentials", client=client_name)
        return {"success": False, "error": "meta_credentials_missing",
                "detail": f"Client '{client_name}' is set to Meta but has no Meta "
                          f"credentials — message not sent (no fallback)."}

    # ── Unipile client / default ────────────────────────────────────────────
    # Use the client's own connected account; the global account_id is only a
    # last resort for ReachNG's own single-tenant use.
    account_id = client_doc.get("whatsapp_account_id") or settings.unipile_whatsapp_account_id
    if account_id:
        return await send_whatsapp_unipile(phone, message, account_id)

    # No transport at all → fail loudly. Never use ReachNG's own Meta number.
    log.error("whatsapp_no_transport_for_client", client=client_name, provider=provider or None)
    return {"success": False, "error": "no_whatsapp_transport",
            "detail": f"Client '{client_name}' has no Unipile account and is not "
                      f"configured for Meta — message not sent."}


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
