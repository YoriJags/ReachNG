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
    parse_label_from_name,
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
async def portal_start_pairing(token: str, label: str = "primary"):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")

    # Silent kill when Unipile isn't paid for — return a clear 503 so the
    # portal can show "WhatsApp pairing is not yet enabled" rather than a
    # generic 500.
    from config import unipile_enabled
    if not unipile_enabled():
        raise HTTPException(
            503,
            "WhatsApp pairing is not yet enabled on this deployment. "
            "Email channel via hello@reachng.ng is active.",
        )

    # Label hygiene — alphanum + underscore, 1-24 chars
    lbl = (label or "primary").strip().lower()
    import re as _re
    if not _re.fullmatch(r"[a-z0-9_]{1,24}", lbl):
        raise HTTPException(400, "label must be 1-24 chars: a-z 0-9 _")

    settings = get_settings()
    link = await start_hosted_auth(
        client_id=str(client["_id"]),
        app_base_url=settings.app_base_url.rstrip("/"),
        label=lbl,
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


# ─── Email pairing (portal, token-gated) ────────────────────────────────────

@router.post("/api/v1/portal/{token}/email/connect/start")
async def portal_start_email_pairing(token: str):
    """Begin connecting a client's email (Gmail/Outlook) via Unipile hosted-auth.
    EYO will then read + reply to their customer emails (HITL), alongside WhatsApp."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")

    from config import unipile_enabled
    if not unipile_enabled():
        raise HTTPException(503, "Email connect is not yet enabled on this deployment.")

    from services.email_pairing import start_email_hosted_auth
    settings = get_settings()
    link = await start_email_hosted_auth(
        client_id=str(client["_id"]),
        app_base_url=settings.app_base_url.rstrip("/"),
    )
    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {
            "email_pairing_pending":    True,
            "email_pairing_link_id":    link["id"],
            "email_pairing_started_at": datetime.now(timezone.utc),
        }},
    )
    return {"url": link["url"], "expires_on": link["expires_on"]}


@router.get("/api/v1/portal/{token}/email/connect/status")
async def portal_email_status(token: str):
    """connected | pending | none — for the portal to poll while connecting."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    if client.get("email_account_id"):
        return {"status": "connected",
                "account_id": client["email_account_id"],
                "since": (client.get("email_connected_at") or "").__str__()}
    if client.get("email_pairing_pending"):
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
    label     = parse_label_from_name(name)  # 'primary' for legacy callbacks

    # Channel routing: the same Unipile webhook delivers WhatsApp AND email
    # pairings. We tag `chan:email` in the name on email connects; fall back to
    # the account type for safety.
    from services.email_pairing import parse_channel_from_name, is_email_account_type
    channel = parse_channel_from_name(name)
    if channel != "email" and is_email_account_type(acc_type):
        channel = "email"

    log.info("unipile_account_webhook_received",
             account_id=account_id, status=status, type=acc_type,
             has_client_id=bool(client_id), label=label, channel=channel)

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

        now = datetime.now(timezone.utc)
        existing = _clients().find_one({"_id": oid},
                                        {"whatsapp_accounts": 1, "whatsapp_account_id": 1})
        if not existing:
            return JSONResponse({"ok": False, "error": "client not found"})

        # ── Email pairing: store on the email slot, not WhatsApp ──────────────
        if channel == "email":
            _clients().update_one({"_id": oid}, {"$set": {
                "email_account_id":      account_id,
                "email_provider":        "unipile",
                "email_connected_at":    now,
                "email_pairing_pending": False,
            }})
            log.info("email_paired", client_id=client_id, account_id=account_id)
            return JSONResponse({"ok": True, "stored": True, "channel": "email"})

        accounts = list(existing.get("whatsapp_accounts") or [])
        # Replace any prior entry with the same label, else append
        accounts = [a for a in accounts if (a.get("label") or "primary") != label]
        is_primary = (label == "primary") or (not accounts)
        if is_primary:
            for a in accounts:
                a["primary"] = False
        accounts.append({
            "label":               label,
            "account_id":          account_id,
            "primary":             is_primary,
            "health":              "OK",
            "paired_at":           now,
            "last_failure_at":     None,
        })

        patch = {
            "whatsapp_accounts":        accounts,
            "whatsapp_provider":        "unipile",
            "whatsapp_connected_at":    now,
            "whatsapp_pairing_pending": False,
        }
        # Maintain backwards compat: keep legacy single-field in sync with primary
        primary_acc = next((a for a in accounts if a.get("primary")), accounts[0])
        patch["whatsapp_account_id"] = primary_acc["account_id"]

        res = _clients().update_one({"_id": oid}, {"$set": patch})
        if res.modified_count:
            log.info("whatsapp_paired", client_id=client_id,
                     account_id=account_id, label=label, is_primary=is_primary)
        return JSONResponse({"ok": True, "stored": bool(res.modified_count), "label": label})

    return JSONResponse({"ok": True, "ignored_status": status})


# ─── Multi-line management (portal, token-gated) ──────────────────────────

class LineLabelPayload(BaseModel):
    label: str


def _sanitised_line(a: dict) -> dict:
    """Strip credentials before sending to the portal client."""
    return {
        "label":           a.get("label") or "primary",
        "account_id":      a.get("account_id"),
        "primary":         bool(a.get("primary")),
        "health":          a.get("health") or "OK",
        "paired_at":       (a.get("paired_at").isoformat() if hasattr(a.get("paired_at"), "isoformat") else a.get("paired_at")),
        "last_failure_at": (a.get("last_failure_at").isoformat() if hasattr(a.get("last_failure_at"), "isoformat") else a.get("last_failure_at")),
    }


@router.get("/api/v1/portal/{token}/whatsapp/lines")
async def portal_list_lines(token: str):
    """Owner-facing list of paired WhatsApp lines on this client."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    accounts = list(client.get("whatsapp_accounts") or [])
    # Surface a legacy single-line client as a one-entry list so the UI is
    # uniform.
    if not accounts and client.get("whatsapp_account_id"):
        accounts = [{
            "label":      "primary",
            "account_id": client["whatsapp_account_id"],
            "primary":    True,
            "health":     "OK",
            "paired_at":  client.get("whatsapp_connected_at"),
        }]
    return {"client": client.get("name"),
            "lines":  [_sanitised_line(a) for a in accounts]}


@router.post("/api/v1/portal/{token}/whatsapp/lines/promote")
async def portal_promote_line(token: str, payload: LineLabelPayload):
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    accounts = list(client.get("whatsapp_accounts") or [])
    target = next((a for a in accounts if (a.get("label") or "primary") == payload.label), None)
    if not target:
        raise HTTPException(404, f"line '{payload.label}' not found")
    for a in accounts:
        a["primary"] = ((a.get("label") or "primary") == payload.label)
    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {"whatsapp_accounts":  accounts,
                  "whatsapp_account_id": target["account_id"]}},
    )
    return {"ok": True, "primary": payload.label}


@router.post("/api/v1/portal/{token}/whatsapp/lines/reset-health")
async def portal_reset_health(token: str, payload: LineLabelPayload):
    """Owner taps after Meta restores the line — clears health flag back to OK."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    res = _clients().update_one(
        {"_id": client["_id"], "whatsapp_accounts.label": payload.label},
        {"$set": {"whatsapp_accounts.$.health":          "OK",
                  "whatsapp_accounts.$.last_failure_at": None}},
    )
    if not res.matched_count:
        raise HTTPException(404, f"line '{payload.label}' not found")
    return {"ok": True, "label": payload.label, "health": "OK"}


@router.post("/api/v1/portal/{token}/whatsapp/lines/remove")
async def portal_remove_line(token: str, payload: LineLabelPayload):
    """Owner removes a backup line. Refuses to remove the only line."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "portal not found")
    accounts = list(client.get("whatsapp_accounts") or [])
    remaining = [a for a in accounts if (a.get("label") or "primary") != payload.label]
    if not remaining:
        raise HTTPException(400, "cannot remove the only paired line — pair a backup first")
    # Ensure something is still primary
    if not any(a.get("primary") for a in remaining):
        remaining[0]["primary"] = True
    primary = next((a for a in remaining if a.get("primary")), remaining[0])
    _clients().update_one(
        {"_id": client["_id"]},
        {"$set": {"whatsapp_accounts":  remaining,
                  "whatsapp_account_id": primary["account_id"]}},
    )
    return {"ok": True, "removed": payload.label, "primary": primary.get("label")}


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


@router.get("/portal/email/connected")
async def email_connected_landing():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Email connected · ReachNG</title>
<meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,sans-serif;background:#FAF6EE;color:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>
<div style='text-align:center;max-width:420px;padding:40px 24px;'>
  <div style='font-size:64px;margin-bottom:16px;'>✓</div>
  <h1 style='font-family:Georgia,serif;font-size:32px;letter-spacing:-1px;margin:0 0 12px;'>Email connected</h1>
  <p style='color:#3d3a33;line-height:1.65;margin:0 0 24px;'>EYO can now read and reply to your customer emails — every reply still waits for your tap. You can close this tab.</p>
  <p style='color:#7a6a3f;font-size:13px;'>Reach<span style='color:#B85C38;'>NG</span></p>
</div></body></html>""")


@router.get("/portal/email/failed")
async def email_failed_landing():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Email connect didn't complete · ReachNG</title>
<meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,sans-serif;background:#FAF6EE;color:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>
<div style='text-align:center;max-width:420px;padding:40px 24px;'>
  <div style='font-size:48px;margin-bottom:16px;color:#c62828;'>!</div>
  <h1 style='font-family:Georgia,serif;font-size:28px;letter-spacing:-1px;margin:0 0 12px;'>Email connect didn't finish</h1>
  <p style='color:#3d3a33;line-height:1.65;margin:0 0 24px;'>The link may have expired or sign-in was cancelled. Open your portal and tap "Connect email" to try again.</p>
  <p style='color:#7a6a3f;font-size:13px;'>Reach<span style='color:#B85C38;'>NG</span></p>
</div></body></html>""")
