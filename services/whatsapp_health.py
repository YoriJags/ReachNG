"""
WhatsApp session-expiry health loop (SPRINT 1 #3).

Why
---
WhatsApp's linked-device sessions expire silently after ~14 days of phone
inactivity. Silent expiry = silent product stop. A paying client could lose
service for a week before anyone notices.

This module runs every 6 hours, asks Unipile for each paired client's
account status, writes the result to the client doc, and alerts both the
owner (us, via OWNER_WHATSAPP) and the client (via their email) the moment
health flips from OK to NOT_OK.

The helpers `get_account_status` and `is_account_healthy` already exist in
`services/whatsapp_pairing.py` — this module wires them into a scheduled
loop with state tracking, owner alerts, and PostHog observability.

Storage on `clients` doc
-----------------------
  whatsapp_health         : "OK" | "DISCONNECTED" | "CREDENTIALS" | "UNKNOWN"
  whatsapp_health_at      : datetime of last successful check
  whatsapp_health_alerted_at : datetime of last alert sent (dedupe across runs)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

from database import get_db
from config import get_settings
from services.whatsapp_pairing import get_account_status, is_account_healthy

log = structlog.get_logger()


# ─── Status normalisation ────────────────────────────────────────────────────

def _status_label(account_doc: Optional[dict]) -> str:
    """Reduce raw Unipile account doc to a single status label we store."""
    if not account_doc:
        return "MISSING"
    sources = account_doc.get("sources") or []
    if not sources:
        return "MISSING"
    statuses = [(s.get("status") or "").upper() for s in sources]
    if all(s == "OK" for s in statuses):
        return "OK"
    if any(s == "CREDENTIALS" for s in statuses):
        return "CREDENTIALS"
    if any(s == "DISCONNECTED" for s in statuses):
        return "DISCONNECTED"
    return "UNKNOWN"


# ─── Owner alert (when a client's health flips OK -> NOT_OK) ─────────────────

async def _alert_health_flipped(client_doc: dict, prev_status: str, new_status: str) -> None:
    """Send WhatsApp alert to owner (us) + email to client when health flips
    from OK to anything else. Best-effort, never blocks the loop."""
    settings = get_settings()
    business = client_doc.get("name", "unknown")
    owner_email = client_doc.get("owner_email")
    portal_token = client_doc.get("portal_token")

    # 1) Alert ReachNG operator via OWNER_WHATSAPP (if configured)
    if settings.owner_whatsapp:
        try:
            from tools.notifier import notify_whatsapp as _notify_owner
            await _notify_owner(
                contact_name=business,
                vertical=client_doc.get("vertical", ""),
                channel="system",
                reply_text=(
                    f"⚠️ WhatsApp session expired for {business}.\n"
                    f"Status: {new_status} (was {prev_status})\n"
                    f"They need to re-scan the QR. Reach out to nudge."
                ),
                intent="system_alert",
                urgency="high",
                summary=f"wa_session_expired · {business} · {new_status}",
            )
        except Exception as exc:
            log.warning("wa_health_owner_alert_failed", error=str(exc), business=business)

    # 2) Email client with reconnect link
    if owner_email and portal_token:
        try:
            from tools.outreach import send_email
            base = (settings.app_base_url or "https://www.reachng.ng").rstrip("/")
            reconnect_url = f"{base}/portal/{portal_token}/connect-whatsapp"
            subject = "Action needed: reconnect EYO to your WhatsApp"
            text = (
                f"Hi {client_doc.get('owner_name', 'there')},\n\n"
                f"EYO has lost its connection to your WhatsApp number. This usually "
                f"happens when your phone is offline for a stretch (~14 days). "
                f"It takes 30 seconds to reconnect.\n\n"
                f"Open this link on the phone with WhatsApp installed:\n{reconnect_url}\n\n"
                f"While disconnected, EYO can't draft replies or read receipts. "
                f"We're standing by to help if anything looks off.\n\n"
                f"— ReachNG\nhello@reachng.ng\n"
            )
            html = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f8f4ec;color:#14110d;margin:0;padding:32px 16px;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8ddc8;border-radius:14px;padding:32px;">
  <div style="font-size:11px;letter-spacing:0.18em;color:#c44a00;text-transform:uppercase;font-weight:700;margin-bottom:14px;">Action needed</div>
  <h1 style="font-family:Georgia,serif;font-size:24px;font-weight:600;letter-spacing:-0.5px;margin:0 0 14px;">Reconnect EYO to your WhatsApp</h1>
  <p style="font-size:15px;line-height:1.65;color:#3a342b;margin:0 0 18px;">EYO has lost its connection to your WhatsApp number. This usually happens when the phone is offline for a stretch (~14 days). It takes 30 seconds to reconnect.</p>
  <p style="margin:0 0 24px;"><a href="{reconnect_url}" style="display:inline-block;background:#14110d;color:#fff;text-decoration:none;padding:14px 22px;border-radius:8px;font-size:14px;font-weight:600;">Reconnect now →</a></p>
  <p style="font-size:13px;line-height:1.65;color:#6b6356;margin:18px 0 0;border-top:1px solid #eee3cf;padding-top:14px;">While disconnected, EYO can't draft replies or read receipts. We're standing by — reply or WhatsApp +234 816 458 3657 if anything looks off.</p>
</div></body></html>"""
            await send_email(
                to_email=owner_email, subject=subject, body=text, html=html,
                force_smtp=True,
            )
            log.info("wa_health_client_email_sent", business=business, email=owner_email)
        except Exception as exc:
            log.warning("wa_health_client_email_failed", error=str(exc), business=business)


# ─── PostHog event ───────────────────────────────────────────────────────────

def _track(event: str, client_id: str, status: str, prev_status: Optional[str] = None) -> None:
    try:
        from services.analytics import track
        track(event,
              distinct_id=f"client:{client_id}",
              client_id=client_id,
              status=status,
              prev_status=prev_status)
    except Exception:
        pass


# ─── The loop itself ─────────────────────────────────────────────────────────

async def run_health_check() -> dict:
    """Iterate all clients with a paired WhatsApp account, check Unipile,
    update health field, alert on flips. Returns summary dict for logs."""
    clients = get_db()["clients"]
    cursor = clients.find(
        {"active": True, "whatsapp_account_id": {"$exists": True, "$ne": None, "$ne": ""}},
        projection={
            "_id": 1, "name": 1, "vertical": 1, "whatsapp_account_id": 1,
            "owner_email": 1, "owner_name": 1, "portal_token": 1,
            "whatsapp_health": 1, "whatsapp_health_alerted_at": 1,
        },
    )

    checked = healthy = unhealthy = flipped = errored = 0
    now = datetime.now(timezone.utc)

    for client_doc in cursor:
        checked += 1
        cid = str(client_doc["_id"])
        acct_id = client_doc["whatsapp_account_id"]
        prev_status = client_doc.get("whatsapp_health") or "UNKNOWN"

        try:
            account = await get_account_status(acct_id)
            new_status = _status_label(account)
        except Exception as exc:
            log.warning("wa_health_check_failed", client_id=cid, error=str(exc))
            new_status = "UNKNOWN"
            errored += 1

        if new_status == "OK":
            healthy += 1
        else:
            unhealthy += 1

        update: dict = {
            "whatsapp_health": new_status,
            "whatsapp_health_at": now,
        }

        # Flip detection: OK -> not OK (alert), or any change (track)
        if prev_status == "OK" and new_status != "OK":
            flipped += 1
            # Dedupe: don't alert same flip twice in 24h
            last_alert = client_doc.get("whatsapp_health_alerted_at")
            should_alert = (
                not last_alert or
                (now - last_alert) > timedelta(hours=24)
            )
            if should_alert:
                await _alert_health_flipped(client_doc, prev_status, new_status)
                update["whatsapp_health_alerted_at"] = now
            _track("wa_session_expired", cid, new_status, prev_status)
        elif prev_status != "OK" and new_status == "OK":
            _track("wa_session_restored", cid, new_status, prev_status)

        clients.update_one({"_id": client_doc["_id"]}, {"$set": update})

    summary = {
        "checked":   checked,
        "healthy":   healthy,
        "unhealthy": unhealthy,
        "flipped":   flipped,
        "errored":   errored,
        "at":        now.isoformat(),
    }
    log.info("wa_health_loop_complete", **summary)
    return summary


def ensure_health_indexes() -> None:
    """Index for fast dashboard queries — find all clients with bad health."""
    get_db()["clients"].create_index(
        [("whatsapp_health", 1), ("active", 1)],
        name="clients_wa_health_active",
        sparse=True,
    )
