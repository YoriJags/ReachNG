"""Meta Instagram + Facebook Messenger transport (EYO channel adapter).

Built on Meta's official Messenger Platform / Instagram Messaging API — the same
Meta App + webhook ReachNG already uses for WhatsApp Cloud API. Inbound DMs
arrive on one webhook (branch on `object`: page=Messenger, instagram=IG); replies
go out via the Graph API with the client's Page access token.

DORMANT by default: the whole channel is off unless `META_MESSAGING_ENABLED` is
true AND a client has Meta messaging configured (page id + token). So it can sit
in the codebase, dev-mode-pilotable, without touching anything live — proven by
tests/test_guardrail_no_external.py.

Pure helpers (signature, parse) are here; the brain handoff is meta_inbound.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

import httpx
import structlog

log = structlog.get_logger()

_GRAPH = "https://graph.facebook.com/v19.0"


def messaging_enabled() -> bool:
    """Global dormant switch — the channel does nothing until this is on."""
    try:
        from config import get_settings
        return bool(getattr(get_settings(), "meta_messaging_enabled", False))
    except Exception:
        return False


def verify_signature(app_secret: Optional[str], raw_body: bytes,
                     header: Optional[str]) -> bool:
    """Verify Meta's X-Hub-Signature-256. When no app_secret is configured we
    skip verification (dev) but log it; in production set META_APP_SECRET."""
    if not app_secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_webhook(body: dict) -> list[dict]:
    """Normalize a Messenger/IG webhook into a flat list of inbound text events:
    [{channel, account_id, sender_id, text}]. Echoes, reactions, and non-text
    are skipped."""
    out: list[dict] = []
    obj = (body or {}).get("object")
    channel = "messenger" if obj == "page" else "instagram" if obj == "instagram" else None
    if not channel:
        return out
    for entry in (body.get("entry") or []):
        account_id = entry.get("id")
        for ev in (entry.get("messaging") or []):
            msg = ev.get("message") or {}
            if msg.get("is_echo"):
                continue
            text = msg.get("text")
            sender = (ev.get("sender") or {}).get("id")
            if account_id and sender and text:
                out.append({
                    "channel":    channel,
                    "account_id": str(account_id),
                    "sender_id":  str(sender),
                    "text":       text,
                })
    return out


async def send_message(account_id: str, page_access_token: str,
                       recipient_id: str, text: str) -> bool:
    """Send a text reply via the Graph API (24h window). Returns True on success."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.post(
                f"{_GRAPH}/{account_id}/messages",
                headers={"Authorization": f"Bearer {page_access_token}"},
                json={
                    "recipient": {"id": recipient_id},
                    "messaging_type": "RESPONSE",
                    "message": {"text": text},
                },
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        log.warning("meta_send_failed", account_id=account_id, error=str(e))
        return False


def client_meta_config(client_doc: Optional[dict]) -> Optional[dict]:
    """Return {account_id, page_token, channel-ids} for a Meta-configured client,
    or None. Page token is decrypted. Matches by page_id or ig_id."""
    if not client_doc:
        return None
    page_id = client_doc.get("meta_page_id")
    ig_id = client_doc.get("meta_ig_id")
    enc = client_doc.get("meta_page_token_enc")
    if not (enc and (page_id or ig_id)):
        return None
    from services.crypto import decrypt
    token = decrypt(enc)
    if not token:
        return None
    return {"page_id": page_id, "ig_id": ig_id, "page_token": token}


async def send_message_for_client(client_doc: dict, channel: str, *,
                                  recipient_id: str, text: str) -> bool:
    """Reply from a client's Page/IG. account_id = ig_id for instagram, else page_id."""
    cfg = client_meta_config(client_doc)
    if not cfg:
        return False
    account_id = cfg["ig_id"] if (channel == "instagram" and cfg.get("ig_id")) else cfg["page_id"]
    if not account_id:
        return False
    return await send_message(account_id, cfg["page_token"], recipient_id, text)
