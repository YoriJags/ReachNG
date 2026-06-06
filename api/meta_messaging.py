"""Meta Instagram + Messenger webhook (verify + receive).

GET  — Meta's subscription handshake (echo hub.challenge if the verify token
       matches WEBHOOK_VERIFY_TOKEN).
POST — signed inbound DMs. Signature-checked (META_APP_SECRET), then DORMANT
       unless META_MESSAGING_ENABLED is on. So it's safe to ship and pilot in
       Dev Mode without affecting anything live.
"""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from config import get_settings

log = structlog.get_logger()
router = APIRouter(tags=["Meta Messaging"])


@router.get("/api/v1/webhooks/meta/messaging")
async def meta_verify(request: Request):
    p = request.query_params
    verify_token = getattr(get_settings(), "webhook_verify_token", None)
    if p.get("hub.mode") == "subscribe" and verify_token and \
       p.get("hub.verify_token") == verify_token:
        return PlainTextResponse(p.get("hub.challenge") or "")
    return PlainTextResponse("forbidden", status_code=403)


@router.post("/api/v1/webhooks/meta/messaging")
async def meta_receive(request: Request):
    raw = await request.body()
    settings = get_settings()
    from services.meta_messaging import verify_signature, parse_webhook, messaging_enabled

    sig = request.headers.get("x-hub-signature-256") or request.headers.get("X-Hub-Signature-256")
    if not verify_signature(getattr(settings, "meta_app_secret", None), raw, sig):
        return JSONResponse({"ok": False, "error": "bad signature"}, status_code=401)

    # Dormant switch — verified but inert until you flip META_MESSAGING_ENABLED.
    if not messaging_enabled():
        return JSONResponse({"ok": True, "dormant": True})

    try:
        body = json.loads(raw or b"{}")
    except Exception:
        body = {}

    from services.meta_inbound import handle_meta_message
    for ev in parse_webhook(body):
        try:
            handle_meta_message(channel=ev["channel"], account_id=ev["account_id"],
                                sender_id=ev["sender_id"], text=ev["text"])
        except Exception:
            pass
    return JSONResponse({"ok": True})
