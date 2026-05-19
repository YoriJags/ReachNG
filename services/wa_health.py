"""
WhatsApp linked-device session health monitor.

Unipile QR pairing creates a "linked device" session that can expire silently
if the owner's phone goes offline for ~14 days or if they manually unlink us
from WhatsApp → Settings → Linked Devices. When that happens, inbound polling
returns nothing and outbound sends fail. Silent stop.

This module periodically asks Unipile for each client's account state, persists
it on the client doc, and fires an alert the moment a session flips OK → NOT_OK.

Wired into the scheduler at 6h cadence (see scheduler.py::_wa_health_check).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from database import get_db
from services.whatsapp_pairing import get_account_status, is_account_healthy

log = structlog.get_logger()


def _clients():
    return get_db()["clients"]


HEALTH_OK = "OK"
HEALTH_BAD = "DISCONNECTED"
HEALTH_UNKNOWN = "UNKNOWN"


async def _check_one(client_doc: dict) -> Optional[dict]:
    """Run a health check on a single client. Returns the new health state."""
    account_id = client_doc.get("whatsapp_account_id")
    if not account_id:
        return None
    try:
        acct = await get_account_status(account_id)
    except Exception as exc:
        log.warning("wa_health_check_fetch_failed",
                    client=client_doc.get("name"), error=str(exc))
        return {"status": HEALTH_UNKNOWN, "reason": str(exc)[:200]}
    if acct is None:
        return {"status": HEALTH_BAD, "reason": "account_not_found_in_unipile"}
    if is_account_healthy(acct):
        return {"status": HEALTH_OK, "reason": None}
    # Capture the offending source(s) for the alert payload
    bad_sources = [
        (s.get("status") or "?").upper()
        for s in (acct.get("sources") or [])
        if (s.get("status") or "").upper() != "OK"
    ]
    return {"status": HEALTH_BAD, "reason": ",".join(bad_sources) or "non_ok"}


async def _alert_on_transition(client_doc: dict, prev: str, new: str) -> None:
    """Fire WhatsApp + email + PostHog when health flips OK → not OK."""
    if not (prev == HEALTH_OK and new != HEALTH_OK):
        return
    name = client_doc.get("name", "(unknown)")
    owner_email = client_doc.get("owner_email")
    owner_name = client_doc.get("owner_name") or "there"
    portal_token = client_doc.get("portal_token")

    # 1) Ping the operator (us) via OWNER_WHATSAPP
    try:
        from tools.notifier import notify_owner
        await notify_owner(
            f"WhatsApp session expired for {name}. "
            f"Owner needs to reconnect: portal /portal/{portal_token}/connect-whatsapp"
        )
    except Exception as exc:
        log.warning("wa_health_owner_notify_failed", client=name, error=str(exc))

    # 2) Email the client
    try:
        from config import get_settings
        from tools.outreach import send_email
        settings = get_settings()
        if owner_email:
            base = (settings.app_base_url or "https://www.reachng.ng").rstrip("/")
            reconnect_url = f"{base}/portal/{portal_token}/connect-whatsapp"
            subject = "Action needed: reconnect EYO to your WhatsApp"
            text = (
                f"Hi {owner_name},\n\n"
                f"EYO's link to your WhatsApp number has expired. This usually "
                f"happens when the phone has been offline for a while, or the "
                f"device was unlinked from WhatsApp → Settings → Linked Devices.\n\n"
                f"Reconnect in 30 seconds: {reconnect_url}\n\n"
                f"Until you reconnect, EYO can't read inbound messages or send "
                f"drafts on your behalf.\n\n"
                f"Anything urgent, reply to this email or WhatsApp +234 816 458 3657.\n\n"
                f"— EYO from ReachNG"
            )
            html = f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f8f4ec;color:#14110d;margin:0;padding:32px 16px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8ddc8;border-radius:14px;padding:32px;">
    <div style="font-size:11px;letter-spacing:0.18em;color:#c62828;text-transform:uppercase;font-weight:700;margin-bottom:18px;">Action needed</div>
    <h1 style="font-family:Georgia,serif;font-size:24px;font-weight:600;letter-spacing:-0.5px;margin:0 0 16px;">Reconnect EYO to your WhatsApp, {owner_name}.</h1>
    <p style="font-size:15px;line-height:1.65;color:#3a342b;margin:0 0 18px;">Your linked-device session has expired. Until you reconnect, EYO can't read inbound messages or send drafts.</p>
    <p style="margin:0 0 24px;">
      <a href="{reconnect_url}" style="display:inline-block;background:#14110d;color:#fff;text-decoration:none;padding:14px 22px;border-radius:8px;font-size:14px;font-weight:600;">Reconnect WhatsApp →</a>
    </p>
    <p style="font-size:13px;line-height:1.65;color:#6b6356;margin:0;">Takes 30 seconds. Open WhatsApp on your phone, Settings, Linked Devices, scan the QR.</p>
    <p style="font-size:12px;color:#9b917f;margin:22px 0 0;">— EYO from ReachNG · hello@reachng.ng</p>
  </div>
</body></html>"""
            await send_email(
                to_email=owner_email, subject=subject, body=text, html=html,
                force_smtp=True,
            )
            log.info("wa_health_client_email_sent", client=name)
    except Exception as exc:
        log.warning("wa_health_client_email_failed", client=name, error=str(exc))

    # 3) PostHog fleet-health dashboard
    try:
        from main import get_posthog
        ph = get_posthog()
        if ph:
            ph.capture(
                "wa_session_expired",
                distinct_id=str(client_doc.get("_id") or name),
                properties={
                    "client_name": name,
                    "vertical": client_doc.get("vertical"),
                    "plan": client_doc.get("plan"),
                },
            )
    except Exception as exc:
        log.warning("wa_health_posthog_failed", client=name, error=str(exc))


async def check_all_clients_wa_health() -> dict:
    """Iterate every active client with a paired WhatsApp account and refresh
    their health field. Fires an alert on each OK → NOT_OK transition.
    Returns summary stats for scheduler logging.
    """
    cursor = _clients().find(
        {"active": True, "whatsapp_account_id": {"$exists": True, "$ne": None}}
    )
    checked = ok = bad = unknown = transitions = 0
    now = datetime.now(timezone.utc)
    for client_doc in cursor:
        result = await _check_one(client_doc)
        if not result:
            continue
        checked += 1
        new_status = result["status"]
        if new_status == HEALTH_OK:
            ok += 1
        elif new_status == HEALTH_BAD:
            bad += 1
        else:
            unknown += 1
        prev_status = client_doc.get("whatsapp_health") or HEALTH_UNKNOWN
        update = {
            "whatsapp_health": new_status,
            "whatsapp_health_reason": result.get("reason"),
            "last_wa_health_check_at": now,
        }
        if prev_status == HEALTH_OK and new_status != HEALTH_OK:
            update["wa_session_expired_at"] = now
            transitions += 1
        _clients().update_one({"_id": client_doc["_id"]}, {"$set": update})
        if prev_status != new_status:
            log.info("wa_health_state_change",
                     client=client_doc.get("name"),
                     prev=prev_status, new=new_status,
                     reason=result.get("reason"))
            await _alert_on_transition(client_doc, prev_status, new_status)

    summary = {"checked": checked, "ok": ok, "bad": bad,
               "unknown": unknown, "transitions": transitions}
    log.info("wa_health_check_done", **summary)
    return summary
