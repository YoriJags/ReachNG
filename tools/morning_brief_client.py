"""
Per-client morning brief — sent at 8am Lagos time to each active client's WhatsApp.

Scoped entirely to one client's data: their overnight bookings/enquiries,
pending approvals, confirmed revenue, and a portal link to approve with one tap.

This is the "hired help" proof-of-concept:
  - Client turns it on, goes to sleep
  - Agent works overnight
  - At 8am: one WhatsApp with everything that happened and what needs attention
"""
from datetime import datetime, timezone, timedelta
from database import get_db
import httpx
import structlog

log = structlog.get_logger()

_LAGOS = timedelta(hours=1)


def _overnight(hours: int = 10) -> datetime:
    """Returns UTC datetime N hours ago (default: covers overnight window)."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _fmt_ngn(n: int | float) -> str:
    if n >= 1_000_000:
        return f"₦{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"₦{n / 1_000:.0f}k"
    return f"₦{int(n)}"


def _get_client_overnight(client_name: str) -> dict:
    """Aggregate overnight activity for one client."""
    since = _overnight(10)  # last 10 hours covers overnight for 8am send
    contacts_col   = get_db()["contacts"]
    approvals_col  = get_db()["pending_approvals"]
    outreach_col   = get_db()["outreach_log"]
    capacity_col   = get_db()["venue_capacity"]

    # New enquiries / replies received overnight (inbound Closer activity)
    new_enquiries = contacts_col.count_documents({
        "client_name": client_name,
        "created_at": {"$gte": since},
    })
    new_replies = get_db()["replies"].count_documents({
        "client_name": client_name,
        "received_at": {"$gte": since},
    })
    interested_replies = get_db()["replies"].count_documents({
        "client_name": client_name,
        "received_at": {"$gte": since},
        "intent": "interested",
    })

    # Messages sent overnight on client's behalf
    messages_sent = outreach_col.count_documents({
        "client_name": client_name,
        "sent_at": {"$gte": since},
    }) if outreach_col is not None else 0

    # Pending approvals scoped to this client
    pending = approvals_col.count_documents({
        "client_name": client_name,
        "status": "pending",
    })

    # Auto-sent count (autopilot)
    auto_sent = approvals_col.count_documents({
        "client_name": client_name,
        "status": "auto_sent",
        "actioned_at": {"$gte": since},
    })

    # Venue capacity — next booking slot (for hospitality clients)
    today = (datetime.now(timezone.utc) + _LAGOS).date().isoformat()
    cap_doc = capacity_col.find_one(
        {"client_name": client_name, "date": today}, {"_id": 0}
    ) if capacity_col is not None else None

    # Deals / bookings confirmed overnight (closed_by_client flag set recently)
    confirmed_bookings = contacts_col.count_documents({
        "client_name": client_name,
        "closed_by_client": True,
        "updated_at": {"$gte": since},
    })

    # Rough deal value if stored
    deal_value = sum(
        d.get("deal_value_ngn", 0) or 0
        for d in contacts_col.find(
            {"client_name": client_name, "closed_by_client": True, "updated_at": {"$gte": since}},
            {"deal_value_ngn": 1},
        )
    )

    return {
        "new_enquiries":     new_enquiries,
        "new_replies":       new_replies,
        "interested_replies": interested_replies,
        "messages_sent":     messages_sent,
        "auto_sent":         auto_sent,
        "pending_approvals": pending,
        "confirmed_bookings": confirmed_bookings,
        "deal_value_ngn":    deal_value,
        "capacity_today":    cap_doc,
    }


def _capacity_line(cap: dict | None) -> str:
    if not cap:
        return ""
    total   = cap.get("total_capacity", 150)
    booked  = cap.get("confirmed_bookings_pax", 0)
    remaining = max(0, total - booked)
    pct = round(booked / total * 100) if total else 0
    if cap.get("is_closed"):
        return "\n🔒 Tonight: venue closed"
    if cap.get("is_private_event"):
        return f"\n🎉 Tonight: private event — fully booked"
    if pct >= 90:
        return f"\n🔴 Tonight: {remaining} pax left — nearly full"
    if pct >= 60:
        return f"\n🟡 Tonight: {remaining} of {total} pax available"
    return f"\n🟢 Tonight: {remaining} of {total} pax available — quiet night"


def compile_client_brief(client_name: str, portal_url: str = "") -> str:
    """
    Build the per-client WhatsApp morning brief.
    Returns the full message string ready to send.
    """
    now_lagos = datetime.now(timezone.utc) + _LAGOS
    day_str   = now_lagos.strftime("%A, %d %b")
    data      = _get_client_overnight(client_name)

    cap_line  = _capacity_line(data["capacity_today"])

    # Overnight activity block
    activity_parts = []
    if data["messages_sent"] or data["auto_sent"]:
        total_out = data["messages_sent"] + data["auto_sent"]
        auto_note = f" ({data['auto_sent']} sent automatically)" if data["auto_sent"] else ""
        activity_parts.append(f"{total_out} messages sent{auto_note}")
    if data["new_enquiries"]:
        activity_parts.append(f"{data['new_enquiries']} new enquir{'y' if data['new_enquiries'] == 1 else 'ies'} came in")
    if data["new_replies"]:
        hot = f" — {data['interested_replies']} 🔥 interested" if data["interested_replies"] else ""
        activity_parts.append(f"{data['new_replies']} repl{'y' if data['new_replies'] == 1 else 'ies'} received{hot}")
    if data["confirmed_bookings"]:
        val = f" ({_fmt_ngn(data['deal_value_ngn'])})" if data["deal_value_ngn"] else ""
        activity_parts.append(f"{data['confirmed_bookings']} booking{'s' if data['confirmed_bookings'] != 1 else ''} confirmed{val}")

    if not activity_parts:
        overnight_block = "Quiet night — no new activity."
    else:
        overnight_block = "\n".join(f"• {p}" for p in activity_parts)

    # Approval nudge
    if data["pending_approvals"]:
        approval_line = (
            f"⚠️ *{data['pending_approvals']} draft{'s' if data['pending_approvals'] != 1 else ''} "
            f"waiting for your approval*"
        )
        if portal_url:
            approval_line += f"\nTap to review: {portal_url}"
    else:
        approval_line = "✅ Approval queue clear — nothing waiting"

    brief = f"""🌅 *Good morning, {client_name.split()[0]}!*
{day_str} — ReachNG overnight report{cap_line}

📬 *LAST NIGHT*
{overnight_block}

{approval_line}

_Powered by ReachNG — your AI sales operator_"""

    return brief.strip()


async def send_client_brief(phone: str, message: str, account_id: str | None = None) -> bool:
    """
    Send the morning brief to a client's WhatsApp via Unipile.
    Uses ReachNG's own Unipile account (operator account, not client's).
    """
    from config import get_settings
    settings = get_settings()
    dsn     = settings.unipile_dsn
    api_key = settings.unipile_api_key
    acct_id = account_id or settings.unipile_whatsapp_account_id

    if not dsn or not api_key or not acct_id:
        log.warning("client_brief_send_skipped_no_credentials", phone=phone)
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://{dsn}/api/v1/chats",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "account_id": acct_id,
                    "attendees_ids": [phone],
                    "text": message,
                },
            )
            resp.raise_for_status()
            log.info("client_brief_sent", phone=phone)
            return True
    except Exception as e:
        log.error("client_brief_send_failed", phone=phone, error=str(e))
        return False


async def run_all_client_briefs() -> dict:
    """
    Called by the scheduler at 8am — sends a brief to every active client
    that has an owner_phone set.
    """
    from api.clients import get_clients
    from api.portal import ensure_client_token

    clients = list(get_clients().find(
        {"active": True, "owner_phone": {"$exists": True, "$ne": None}},
        {"name": 1, "owner_phone": 1, "portal_token": 1},
    ))

    sent = 0
    skipped = 0

    for c in clients:
        phone = c.get("owner_phone")
        name  = c.get("name")
        if not phone:
            skipped += 1
            continue

        # Get portal URL for the approval tap-through
        try:
            from config import get_settings
            settings = get_settings()
            base_url = getattr(settings, "app_base_url", "https://reachng.railway.app")
            token    = ensure_client_token(name)
            portal_url = f"{base_url}/portal/{token}"
        except Exception:
            portal_url = ""

        message = compile_client_brief(name, portal_url)
        ok = await send_client_brief(phone, message)
        if ok:
            sent += 1
        else:
            skipped += 1

    log.info("client_briefs_run", sent=sent, skipped=skipped)
    return {"sent": sent, "skipped": skipped}
