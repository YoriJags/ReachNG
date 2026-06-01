"""
Resend email-event webhook receiver.

Resend posts events to this endpoint on every email lifecycle change:
  - email.sent       — picked up by their servers
  - email.delivered  — recipient's MTA accepted it
  - email.opened     — recipient's mail client loaded the tracking pixel
  - email.clicked    — recipient tapped a tracked link in the email
  - email.bounced    — hard bounce
  - email.complained — marked as spam
  - email.delivery_delayed

We match each event to the right outreach_log row by `provider_message_id`
(Resend's email id, which we store when send_email returns it) and update
the analytics fields in-place. From there the outreach analytics dashboard
reads delivered_at / opened_at / clicked_at / bounced_at / etc.

Webhook setup in Resend:
  Dashboard -> Webhooks -> Add endpoint -> https://www.reachng.ng/api/v1/webhooks/resend
  Subscribe to all email.* events.
  Set the signing secret as RESEND_WEBHOOK_SECRET in Railway.

Security: Resend signs every webhook with the secret via the
`Resend-Signing-Secret` (or `svix-signature` depending on the integration)
header. We verify it before touching Mongo.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Request, Response, HTTPException

from config import get_settings
from database import get_outreach_log

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/webhooks", tags=["ResendWebhook"])


def _tail(reason: str) -> None:
    """Send a webhook-failure breadcrumb to Sentry (no-op until SENTRY_DSN set)."""
    try:
        from tools.observability import capture_message
        capture_message(f"webhook_failure: {reason}", level="warning", integration="resend")
    except Exception:
        pass


# Resend ships either a Svix-style signature or a simple secret-header
# depending on the dashboard config. We accept both.
SVIX_HEADER          = "svix-signature"
SVIX_ID_HEADER       = "svix-id"
SVIX_TIMESTAMP       = "svix-timestamp"
SIMPLE_SECRET_HEADER = "resend-signing-secret"


def _verify_svix(raw_body: bytes, headers: dict, secret: str) -> bool:
    """Svix signature: 'v1,<base64-hmac-sha256>'."""
    sig_header = headers.get(SVIX_HEADER) or ""
    msg_id     = headers.get(SVIX_ID_HEADER) or ""
    timestamp  = headers.get(SVIX_TIMESTAMP) or ""
    if not (sig_header and msg_id and timestamp):
        return False
    try:
        import base64
        secret_bytes = base64.b64decode(secret.split("_", 1)[1]) if secret.startswith("whsec_") else secret.encode()
        signed_content = f"{msg_id}.{timestamp}.{raw_body.decode('utf-8')}".encode()
        expected = base64.b64encode(
            hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
        ).decode()
        # sig_header can carry multiple comma-separated signatures like 'v1,xxx v1,yyy'
        for sig in sig_header.split():
            version, _, value = sig.partition(",")
            if version == "v1" and hmac.compare_digest(value, expected):
                return True
    except Exception:
        pass
    return False


def _verify_simple(headers: dict, secret: str) -> bool:
    provided = headers.get(SIMPLE_SECRET_HEADER)
    return bool(provided and hmac.compare_digest(provided, secret))


def _ev_ts(event: dict) -> datetime:
    raw = event.get("created_at") or event.get("emitted_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)


@router.post("/resend")
async def resend_webhook(request: Request):
    settings = get_settings()
    secret = getattr(settings, "resend_webhook_secret", None) or getattr(settings, "resend_signing_secret", None)
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    is_prod = (getattr(settings, "app_env", "") or "").lower() == "production"

    if secret:
        if not (_verify_svix(raw_body, headers, secret) or _verify_simple(headers, secret)):
            log.warning("resend_webhook_signature_invalid")
            _tail("resend signature invalid")
            raise HTTPException(401, "bad signature")
    elif is_prod:
        # Fail closed in production: a missing RESEND_WEBHOOK_SECRET must not
        # mean "accept everything". Set the secret in Railway to enable events.
        log.error("resend_webhook_secret_unset_in_prod")
        _tail("resend secret unset in prod")
        raise HTTPException(401, "webhook secret not configured")

    try:
        payload = json.loads(raw_body or b"{}")
    except Exception:
        return {"ok": True}

    event_type = (payload.get("type") or "").lower()
    data       = payload.get("data") or {}
    email_id   = data.get("email_id") or data.get("id")
    to_email   = (data.get("to") or [None])[0] if isinstance(data.get("to"), list) else data.get("to")

    if not email_id:
        return {"ok": True, "ignored": "no_email_id"}

    log_col = get_outreach_log()
    now     = _ev_ts(payload)

    # Match the outreach_log row by provider_message_id, with to_email as fallback
    query = {"provider_message_id": email_id}
    if not log_col.find_one(query, {"_id": 1}) and to_email:
        query = {"to_email": to_email, "provider_message_id": None}

    update: dict = {"$set": {}}
    if event_type in ("email.delivered", "email.sent"):
        update["$set"]["delivered_at"] = now
    elif event_type == "email.opened":
        update["$set"]["opened_at"] = now
        update["$min"] = {"first_open_at": now}
        update["$inc"] = {"open_count": 1}
    elif event_type == "email.clicked":
        update["$set"]["clicked_at"] = now
        update.setdefault("$inc", {})["click_count"] = 1
    elif event_type == "email.bounced":
        update["$set"]["bounced_at"]    = now
        update["$set"]["bounce_reason"] = (data.get("bounce") or {}).get("message")
    elif event_type == "email.complained":
        update["$set"]["complained_at"] = now
    else:
        return {"ok": True, "ignored": event_type}

    res = log_col.update_one(query, update)
    log.info("resend_event_recorded",
             type=event_type, email_id=email_id,
             matched=bool(res.matched_count))
    return {"ok": True, "matched": bool(res.matched_count)}
