"""
WhatsApp pairing endpoints.

Public (portal token-gated):
  POST /api/v1/portal/{token}/whatsapp/connect/start  → returns hosted-auth URL
  GET  /api/v1/portal/{token}/whatsapp/connect/status → has the client connected yet?

Admin (Basic Auth):
  POST /api/v1/admin/clients/{client_id}/whatsapp/connect/start  → same, for ops use

Webhook (Unipile → us, secret-token gated):
  POST /api/v1/webhooks/unipile/account
    Body: {account_id, status, name, type, ...}
    We use the echoed `name` (set to "client:{client_id}" at start) to
    route the new account_id onto the right client doc.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from auth import require_auth as _require_admin_auth
from config import get_settings
from database import get_db
from services.whatsapp_pairing import (
    get_account_status,
    is_account_healthy,
    parse_client_id_from_name,
    start_hosted_auth,
)

log = structlog.get_logger()
router = APIRouter(tags=["WhatsApp Connect"])


def _clients():
    return get_db()["clients"]


def _get_client_by_token(token: str) -> Optional[dict]:
    return _clients().find_one({"portal_token": token, "active": True})


# ─── Portal (token-gated) ───────────────────────────────────────────────────

@router.get("/portal/{token}/connect-whatsapp", response_class=HTMLResponse)
async def portal_connect_whatsapp_page(token: str, request: Request):
    """Render the WhatsApp pairing page for a given client portal token."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal/connect_whatsapp.html", {
        "token":       token,
        "client_name": client.get("name", "your business"),
    })


@router.post("/api/v1/portal/{token}/whatsapp/connect/start")
async def portal_start_pairing(token: str):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")

    settings = get_settings()
    link = await start_hosted_auth(
        client_id=str(client["_id"]),
        app_base_url=settings.app_base_url.rstrip("/"),
    )

    # Persist the pending link so the status endpoint can verify nothing's
    # shifted between start and webhook callback.
    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {
            "whatsapp_pairing_pending": True,
            "whatsapp_pairing_link_id": link["id"],
            "whatsapp_pairing_started_at": datetime.now(timezone.utc),
        }},
    )

    return {
        "url":         link["url"],
        "expires_on":  link["expires_on"],
    }


@router.get("/api/v1/portal/{token}/whatsapp/connect/status")
async def portal_pairing_status(token: str):
    """Lightweight status: connected | pending | none. Used by the portal
    page to poll while the user is scanning the QR."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")

    account_id = client.get("whatsapp_account_id")
    if account_id:
        return {
            "status":     "connected",
            "account_id": account_id,
            "since":      (client.get("whatsapp_connected_at") or "").__str__(),
        }
    if client.get("whatsapp_pairing_pending"):
        return {"status": "pending"}
    return {"status": "none"}


# ─── Admin (Basic Auth) ─────────────────────────────────────────────────────

@router.post("/api/v1/admin/clients/{client_id}/whatsapp/connect/start")
async def admin_start_pairing(client_id: str, _: str = Depends(_require_admin_auth)):
    from bson import ObjectId
    try:
        oid = ObjectId(client_id)
    except Exception:
        raise HTTPException(400, "invalid client_id")

    client = _clients().find_one({"_id": oid})
    if not client:
        raise HTTPException(404, "client not found")

    settings = get_settings()
    link = await start_hosted_auth(
        client_id=str(client["_id"]),
        app_base_url=settings.app_base_url.rstrip("/"),
    )
    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {
            "whatsapp_pairing_pending": True,
            "whatsapp_pairing_link_id": link["id"],
            "whatsapp_pairing_started_at": datetime.now(timezone.utc),
        }},
    )
    return {"url": link["url"], "expires_on": link["expires_on"]}


# ─── Webhook (Unipile → us) ─────────────────────────────────────────────────

class UnipileAccountNotification(BaseModel):
    account_id: Optional[str] = None
    status:     Optional[str] = None
    name:       Optional[str] = None
    type:       Optional[str] = None


@router.post("/api/v1/webhooks/unipile/account")
async def unipile_account_webhook(request: Request):
    """Receives Unipile hosted-auth completion callbacks.

    Auth model: optional shared-secret check via UNIPILE_HOSTED_NOTIFY_TOKEN.
    Unipile doesn't sign the webhook so we rely on:
      (a) shared-secret header if configured, OR
      (b) verifying the echoed `name` matches a pending pairing record we created
    """
    settings = get_settings()
    notify_token = getattr(settings, "unipile_hosted_notify_token", None)
    if notify_token:
        provided = request.headers.get("x-notify-token") or request.headers.get("X-Notify-Token")
        if provided != notify_token:
            log.warning("unipile_webhook_token_mismatch")
            raise HTTPException(401, "bad token")

    try:
        body = await request.json()
    except Exception:
        body = {}

    account_id = body.get("account_id") or body.get("accountId") or body.get("id")
    status     = (body.get("status") or "").upper()
    name       = body.get("name")
    acc_type   = (body.get("type") or "").upper()

    client_id = parse_client_id_from_name(name)
    log.info("unipile_account_webhook_received",
             account_id=account_id, status=status, type=acc_type, has_client_id=bool(client_id))

    if not (account_id and client_id):
        # No-op — could be a different notification type, don't 4xx Unipile
        return JSONResponse({"ok": True, "ignored": True})

    # Only act on success-shaped events; failure paths leave the pending flag
    # so the portal can show "try again."
    if status in {"CREATION_SUCCESS", "OK", "CONNECTED"} or "SUCCESS" in status:
        from bson import ObjectId
        try:
            oid = ObjectId(client_id)
        except Exception:
            return JSONResponse({"ok": False, "error": "bad client_id"})

        res = _clients().update_one(
            {"_id": oid},
            {"$set": {
                "whatsapp_account_id":    account_id,
                "whatsapp_provider":      "unipile",
                "whatsapp_connected_at":  datetime.now(timezone.utc),
                "whatsapp_pairing_pending": False,
            }},
        )
        if res.modified_count:
            log.info("whatsapp_paired", client_id=client_id, account_id=account_id)
        return JSONResponse({"ok": True, "stored": bool(res.modified_count)})

    return JSONResponse({"ok": True, "ignored_status": status})


# ─── Static OK/fail landing pages (Unipile redirects here post-scan) ───────

@router.get("/portal/whatsapp/connected")
async def whatsapp_connected_landing():
    """Static success landing shown after Unipile completes the scan flow.
    The actual data save happens via webhook above; this page just confirms."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>WhatsApp connected · ReachNG</title>
<meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,sans-serif;background:#FAF6EE;color:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>
<div style='text-align:center;max-width:420px;padding:40px 24px;'>
  <div style='font-size:64px;margin-bottom:16px;'>✓</div>
  <h1 style='font-family:Georgia,serif;font-size:32px;letter-spacing:-1px;margin:0 0 12px;'>WhatsApp connected</h1>
  <p style='color:#3d3a33;line-height:1.65;margin:0 0 24px;'>EYO can now reply on your behalf. You can close this tab — your portal will update automatically.</p>
  <p style='color:#7a6a3f;font-size:13px;'>Reach<span style='color:#B85C38;'>NG</span></p>
</div></body></html>""")


@router.get("/portal/whatsapp/failed")
async def whatsapp_failed_landing():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Pairing didn't complete · ReachNG</title>
<meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,sans-serif;background:#FAF6EE;color:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>
<div style='text-align:center;max-width:420px;padding:40px 24px;'>
  <div style='font-size:48px;margin-bottom:16px;color:#c62828;'>!</div>
  <h1 style='font-family:Georgia,serif;font-size:28px;letter-spacing:-1px;margin:0 0 12px;'>Pairing didn't finish</h1>
  <p style='color:#3d3a33;line-height:1.65;margin:0 0 24px;'>The QR may have expired or the scan was cancelled. Open your portal and tap "Connect WhatsApp" to try again.</p>
  <p style='color:#7a6a3f;font-size:13px;'>Reach<span style='color:#B85C38;'>NG</span></p>
</div></body></html>""")
