"""
Proactive Intelligence — festival timing (T0.5, behaviour 1).

The "agent acts without being asked" moat. When a Nigerian festive window
opens, EYO drafts a re-engagement message to each client's dormant customers
and drops it in the HITL queue — the owner wakes up to "ready to send" festive
nudges they never had to think about.

Bounded + safe:
  • Only fires inside a festival window (a handful of days/year).
  • Capped per client per festival; deduped via `proactive_log` so the same
    customer is never nudged twice for the same festival.
  • Routes through tools.hitl.queue_draft — owner approves before anything sends,
    and the existing account caps / warmup ramp still apply.

Fixed-date festivals only for v1. Variable-date ones (Eid, Easter) are a TODO —
better to omit than to fire on the wrong day.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import structlog

from database import get_db
from tools.hitl import queue_draft

log = structlog.get_logger()

DORMANT_AFTER_DAYS = 21
PER_CLIENT_CAP = 15

# Each window is (month, day) inclusive. Windows may wrap the year end.
FESTIVALS = [
    {"key": "valentine",    "name": "Valentine's",      "start": (2, 8),  "end": (2, 14),
     "template": "Happy Valentine's{name}! 💝 We've got something special lined up for the season — reply and let's sort you out before it's fully booked."},
    {"key": "workers_day",  "name": "Workers' Day",      "start": (4, 29), "end": (5, 1),
     "template": "Happy Workers' Day{name}! 🎉 Treat yourself this long weekend — reply and we'll set you up."},
    {"key": "democracy_day","name": "Democracy Day",     "start": (6, 10), "end": (6, 12),
     "template": "Happy Democracy Day{name}! 🇳🇬 We're open and ready for you this holiday — reply to lock something in."},
    {"key": "independence", "name": "Independence Day",   "start": (9, 28), "end": (10, 1),
     "template": "Happy Independence Day{name}! 🇳🇬 We've planned something for the celebrations — reply and let's get you sorted."},
    {"key": "detty_december","name": "Detty December",    "start": (12, 1), "end": (12, 26),
     "template": "It's Detty December{name}! 🎉 The season fills up fast — reply now and we'll hold a spot for you before it's gone."},
    {"key": "new_year",     "name": "New Year",           "start": (12, 27), "end": (1, 2),
     "template": "Happy New Year{name}! 🥂 Start the year with us — reply and we'll get you booked in."},
]


def _in_window(today: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    md = (today.month, today.day)
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end          # wraps the year boundary


def active_festival(today: datetime | None = None) -> dict | None:
    """Return the festival whose window contains `today` (Lagos date), else None."""
    if today is None:
        today = datetime.now(timezone.utc) + timedelta(hours=1)   # Africa/Lagos
    for f in FESTIVALS:
        if _in_window(today, f["start"], f["end"]):
            return f
    return None


def render_festival_message(festival: dict, contact_name: str | None, signature: str = "") -> str:
    first = (contact_name or "").strip().split(" ")[0] if contact_name else ""
    name_part = f", {first}" if first and first.lower() not in ("there", "unknown", "—") else ""
    body = festival["template"].format(name=name_part)
    if signature:
        body += f"\n— {signature}"
    return body


def draft_festival_nudges(client: dict, festival: dict, limit: int = PER_CLIENT_CAP) -> int:
    """Queue (HITL) festive re-engagement drafts for one client's dormant
    customers. Returns the number queued."""
    db = get_db()
    name = client.get("name")
    if not name:
        return 0

    plog = db["proactive_log"]
    already = {
        d.get("phone") for d in plog.find(
            {"client_name": name, "festival_key": festival["key"]}, {"phone": 1}
        )
    }

    cutoff = datetime.now(timezone.utc) - timedelta(days=DORMANT_AFTER_DAYS)
    # Oldest-contacted first = most dormant. Missing last_contacted_at sorts first.
    candidates = db["contacts"].find(
        {"client_name": name,
         "phone": {"$nin": [None, ""]},
         "status": {"$nin": ["opted_out", "blocked", "unsubscribed", "do_not_contact"]}},
        {"name": 1, "phone": 1, "vertical": 1, "last_contacted_at": 1, "created_at": 1},
    ).sort("last_contacted_at", 1).limit(limit * 5)

    signature = (client.get("signature") or "").strip()
    vertical = client.get("vertical") or "general"
    queued = 0

    for c in candidates:
        if queued >= limit:
            break
        phone = c.get("phone")
        if not phone or phone in already:
            continue
        # Respect dormancy: skip anyone contacted within the window.
        last = c.get("last_contacted_at")
        if isinstance(last, datetime) and last > cutoff:
            continue
        msg = render_festival_message(festival, c.get("name"), signature)
        try:
            queue_draft(
                contact_id=str(c.get("_id")),
                contact_name=c.get("name") or "there",
                vertical=vertical,
                channel="whatsapp",
                message=msg,
                phone=phone,
                source="proactive_festival",     # transactional source — skips prospecting brief gate
                client_name=name,
            )
            plog.insert_one({
                "client_name":  name,
                "festival_key": festival["key"],
                "phone":        phone,
                "created_at":   datetime.now(timezone.utc),
            })
            queued += 1
        except Exception as e:
            # Account-cap / warmup limits land here — stop trying this client.
            log.info("proactive_festival_skip", client=name, reason=str(e)[:80])
            break

    if queued:
        log.info("proactive_festival_queued", client=name, festival=festival["key"], count=queued)
    return queued
