"""
Off-boarding flow (SPRINT 3 — pre-paid-client safety net).

When a client cancels, the playbook needs to fire cleanly:
  1. Cancel future billing (just flag, no Paystack disable — they keep
     the rest of the paid period)
  2. Mark client inactive + record cancellation metadata
  3. Best-effort unpair their WhatsApp via Unipile (so we stop reading
     their inbound the moment they say bye)
  4. Send a branded farewell email with their data-export link + 30-day
     reactivation discount + a one-question survey
  5. Alert operator on OWNER_WHATSAPP so we know to follow up personally
  6. PostHog `client_offboarded` event with churn_reason + tenure

Storage on `clients` doc
-----------------------
  active = False
  offboarded_at = datetime
  offboarded_reason = string (free text from owner)
  offboarded_by = "owner" | "operator" | "auto"
  reactivation_code = short token for the 30-day discount (optional)
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Optional

import structlog

from database import get_db
from config import get_settings

log = structlog.get_logger()


def _clients():
    return get_db()["clients"]


# ─── Public ──────────────────────────────────────────────────────────────────

async def offboard_client(
    client_name: str,
    *,
    reason: str = "",
    by: str = "owner",
    skip_alerts: bool = False,
) -> dict:
    """Run the full off-boarding playbook. Returns a summary dict."""
    clients = _clients()
    client = clients.find_one(
        {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}}
    )
    if not client:
        return {"ok": False, "error": "client_not_found", "client": client_name}

    if client.get("active") is False and client.get("offboarded_at"):
        return {"ok": False, "error": "already_offboarded", "client": client_name,
                "offboarded_at": client.get("offboarded_at").isoformat() if client.get("offboarded_at") else None}

    now = datetime.now(timezone.utc)
    onboarded_at = (client.get("onboarded_at")
                    or client.get("client_onboarded_at")
                    or client.get("created_at")
                    or now)
    try:
        tenure_days = max(0, int((now - onboarded_at).total_seconds() / 86400))
    except Exception:
        tenure_days = 0
    reactivation_code = "RENEW-" + secrets.token_urlsafe(6).upper()

    # ── 1+2: Mark inactive, write churn metadata ─────────────────────────────
    clients.update_one(
        {"_id": client["_id"]},
        {"$set": {
            "active":                False,
            "payment_status":        "cancelled",
            "offboarded_at":         now,
            "offboarded_reason":     (reason or "")[:1000],
            "offboarded_by":         by,
            "tenure_days_at_churn":  tenure_days,
            "reactivation_code":     reactivation_code,
            "updated_at":            now,
        }},
    )

    # ── 3: Best-effort WhatsApp unpair via Unipile ───────────────────────────
    unpair_result = "skipped"
    acct_id = client.get("whatsapp_account_id")
    if acct_id:
        try:
            settings = get_settings()
            if settings.unipile_dsn and settings.unipile_api_key:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as cli:
                    resp = await cli.delete(
                        f"https://{settings.unipile_dsn}/api/v1/accounts/{acct_id}",
                        headers={"X-API-KEY": settings.unipile_api_key},
                    )
                    unpair_result = f"unpaired_{resp.status_code}"
        except Exception as exc:
            unpair_result = f"failed:{str(exc)[:80]}"
            log.warning("offboard_unpair_failed", client=client_name, error=str(exc))

    # ── 4: Farewell email ────────────────────────────────────────────────────
    email_result = "skipped_no_email"
    if not skip_alerts and client.get("owner_email"):
        try:
            email_result = await _send_farewell_email(client, reactivation_code, tenure_days)
        except Exception as exc:
            log.warning("offboard_email_failed", client=client_name, error=str(exc))
            email_result = f"failed:{str(exc)[:80]}"

    # ── 5: Operator alert ────────────────────────────────────────────────────
    if not skip_alerts:
        try:
            settings = get_settings()
            if settings.owner_whatsapp:
                from tools.notifier import notify_whatsapp as _notify
                await _notify(
                    contact_name=client["name"],
                    vertical=client.get("vertical", ""),
                    channel="system",
                    reply_text=(
                        f"⚠️ {client['name']} just off-boarded ({by}).\n"
                        f"Tenure: {tenure_days}d. Reason: {reason[:200] or '(none given)'}\n"
                        f"Reactivation code: {reactivation_code}"
                    ),
                    intent="system_alert",
                    urgency="high",
                    summary=f"client_offboarded · {client['name']}",
                )
        except Exception as exc:
            log.warning("offboard_operator_alert_failed", error=str(exc))

    # ── 6: PostHog ───────────────────────────────────────────────────────────
    try:
        from services.analytics import track
        track("client_offboarded",
              distinct_id=f"client:{client['_id']}",
              client_id=str(client["_id"]),
              client_name=client["name"],
              vertical=client.get("vertical"),
              plan=client.get("plan"),
              tenure_days=tenure_days,
              offboarded_by=by,
              has_reason=bool(reason))
    except Exception:
        pass

    log.info("client_offboarded", client=client_name, by=by, tenure_days=tenure_days,
             unpair=unpair_result, email=email_result)

    return {
        "ok":                True,
        "client":            client_name,
        "tenure_days":       tenure_days,
        "reactivation_code": reactivation_code,
        "unpair":            unpair_result,
        "email":             email_result,
    }


# ─── Farewell email ──────────────────────────────────────────────────────────

async def _send_farewell_email(client: dict, reactivation_code: str, tenure_days: int) -> str:
    settings = get_settings()
    base = (settings.app_base_url or "https://www.reachng.ng").rstrip("/")
    portal_token = client.get("portal_token") or ""
    owner_name = client.get("owner_name") or "there"
    business = client.get("name") or "your business"

    # Single-question survey: a mailto link with subject pre-filled keeps it dead simple
    survey_to = "hello@reachng.ng"
    survey_subject = f"Why I left ReachNG — {business}"
    survey_link = (
        f"mailto:{survey_to}?subject={survey_subject.replace(' ', '%20')}"
        f"&body=One sentence: what would've kept me on EYO was…"
    )
    export_url = f"{base}/portal/{portal_token}/data-export" if portal_token else f"{base}/contact"

    subject = "You're off-boarded. Door stays open."
    text = (
        f"Hi {owner_name},\n\n"
        f"EYO is no longer drafting replies on your WhatsApp as of today. "
        f"Here's what's done and what you can still do:\n\n"
        f"• Your subscription is cancelled. You will not be charged again.\n"
        f"• WhatsApp pairing has been unlinked from our side.\n"
        f"• Your customer memory + conversation history is still saved. "
        f"  Export it from the portal: {export_url}\n\n"
        f"If something we did pushed you out, I'd genuinely like to know.\n"
        f"One sentence is enough: {survey_to}\n\n"
        f"And if you decide to come back in the next 30 days, this code "
        f"gives you 30% off your first 3 months back: {reactivation_code}\n\n"
        f"Thank you for trusting us with {business}'s WhatsApp for {tenure_days} days.\n\n"
        f"— Yori\nReachNG · hello@reachng.ng\n"
    )
    html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f8f4ec;color:#14110d;margin:0;padding:32px 16px;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8ddc8;border-radius:14px;padding:32px;">
  <div style="font-size:11px;letter-spacing:0.18em;color:#c44a00;text-transform:uppercase;font-weight:700;margin-bottom:14px;">Off-boarded</div>
  <h1 style="font-family:Georgia,serif;font-size:24px;font-weight:600;letter-spacing:-0.4px;margin:0 0 14px;">Door stays open, {owner_name}.</h1>
  <p style="font-size:15px;line-height:1.65;color:#3a342b;margin:0 0 14px;">EYO is no longer drafting on <strong>{business}</strong>'s WhatsApp as of today.</p>
  <ul style="font-size:14px;line-height:1.7;color:#3a342b;padding-left:20px;margin:0 0 20px;">
    <li>Subscription <strong>cancelled</strong> — no further charges.</li>
    <li>WhatsApp pairing <strong>unlinked</strong> from our side.</li>
    <li>Your customer memory + conversation history is <strong>still saved</strong>. <a href="{export_url}" style="color:#c44a00;">Export from your portal →</a></li>
  </ul>
  <p style="margin:0 0 18px; padding: 14px 16px; background: rgba(255,85,0,0.06); border-left: 3px solid #c44a00; border-radius: 6px; font-size: 14px; line-height: 1.65; color: #3a342b;">
    Coming back in the next 30 days? <strong style="color:#14110d;">{reactivation_code}</strong> gives you 30% off your first 3 months back.
  </p>
  <p style="margin:0 0 20px;font-size:14px;color:#3a342b;line-height:1.65;">If we pushed you out — I'd genuinely like to know. One sentence is enough:</p>
  <p style="margin:0 0 24px;"><a href="{survey_link}" style="display:inline-block;background:#14110d;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-size:13px;font-weight:600;">Tell us why →</a></p>
  <p style="font-size:13px;line-height:1.65;color:#6b6356;margin:24px 0 0;border-top:1px solid #eee3cf;padding-top:18px;">Thank you for trusting us with {business}'s WhatsApp for {tenure_days} days.<br>— Yori · ReachNG · hello@reachng.ng</p>
</div></body></html>"""

    try:
        from tools.outreach import send_email
        await send_email(
            to_email=client["owner_email"], subject=subject,
            body=text, html=html, force_smtp=True,
        )
        return "sent"
    except Exception as exc:
        log.warning("offboard_email_send_failed", error=str(exc), client=client["name"])
        return f"failed:{str(exc)[:80]}"


def ensure_offboarding_indexes() -> None:
    coll = _clients()
    coll.create_index(
        [("active", 1), ("offboarded_at", -1)],
        name="clients_offboarded_recent", sparse=True,
    )
    coll.create_index(
        [("reactivation_code", 1)],
        name="clients_reactivation_code", sparse=True, unique=True,
    )
