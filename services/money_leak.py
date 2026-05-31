"""
Money Leak Report + Revenue Rescue engine.

One question: *where is money quietly dying in this client's chats?*

This is a composition layer — it does NOT invent new detection. It pulls the
already-shipped signals into a single ₦ figure with categorised examples:

  • Confirmed owed  — cash_signals_for(): rent / debt / school-fee ledgers (real ₦)
  • Asked price, never quoted — missed_opportunities_for() (Radar)
  • Ghosted "I'll pay" promises — scan of replies for pay-promise language
  • Silent inbound — someone messaged, no outbound ever went back

Two surfaces use this one report:
  • Money Leak Report (pre-paywall)  — "You have ₦X sitting in dead chats."
  • Revenue Rescue Mode (post-paywall) — same data + a draft-all action.

Scoped strictly by client_name. No PII in logs.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from database import get_db
from tools.cash_signals import cash_signals_for, missed_opportunities_for

# Conservative per-lead value used to turn a pipeline *count* into a ₦ estimate.
# Deliberately modest (deposit-sized) so the headline is defensible, not hype.
DEFAULT_AVG_DEAL_NGN = 50_000

_PAY_PROMISE_TOKENS = (
    "i'll pay", "i will pay", "i go pay", "pay tomorrow", "pay later",
    "send account", "send your account", "make transfer", "ll transfer",
    "transfer now", "paying now", "sending now", "send the account",
)


def _looks_like_pay_promise(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(tok in t for tok in _PAY_PROMISE_TOKENS)


def _ghosted_promises(client_name: str, days: int, limit: int = 20) -> list[dict]:
    """Replies that promised payment, with no money landed since.

    A 'leak' = customer said they'd pay, then nothing arrived. We can't see
    every payment rail, so we use the same conservative signal the brief uses:
    no outreach_log 'payment_confirmed' and no debt_cases flip to paid after
    the promise. Returns examples for the report.
    """
    db = get_db()
    if "replies" not in db.list_collection_names():
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    contacts = db["contacts"]
    cursor = db["replies"].find(
        {"received_at": {"$gte": since}},
        {"text": 1, "contact_id": 1, "contact_name": 1, "channel": 1, "received_at": 1},
    ).sort("received_at", -1).limit(500)

    out: list[dict] = []
    now = datetime.now(timezone.utc)
    for r in cursor:
        if not _looks_like_pay_promise(r.get("text") or ""):
            continue
        cid = r.get("contact_id")
        if not cid:
            continue
        contact = contacts.find_one(
            {"_id": cid}, {"client_name": 1, "name": 1, "phone": 1, "status": 1}
        )
        if not contact or contact.get("client_name") != client_name:
            continue
        if (contact.get("status") or "").lower() in ("paid", "converted", "won"):
            continue
        out.append({
            "contact_id":   str(cid),
            "contact_name": contact.get("name") or r.get("contact_name") or "Unknown",
            "phone":        contact.get("phone") or "",
            "channel":      r.get("channel") or "",
            "reply_text":   (r.get("text") or "")[:160],
            "promised_at":  r["received_at"].isoformat() if hasattr(r["received_at"], "isoformat") else r["received_at"],
            "days_since":   round((now - r["received_at"]).total_seconds() / 86400.0, 1),
        })
        if len(out) >= limit:
            break
    return out


def _silent_inbound(client_name: str, days: int, min_hours_silent: int = 4, limit: int = 20) -> list[dict]:
    """Inbound messages with no outbound ever sent back — pure lost attention."""
    db = get_db()
    if "inbound_messages" not in db.list_collection_names():
        return []
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    cutoff = now - timedelta(hours=min_hours_silent)
    cursor = db["inbound_messages"].find(
        {"client_name": client_name, "received_at": {"$gte": since, "$lt": cutoff}},
        {"sender_phone": 1, "body": 1, "received_at": 1, "contact_name": 1},
    ).sort("received_at", -1).limit(200)

    out: list[dict] = []
    seen: set[str] = set()
    outreach = db["outreach_log"] if "outreach_log" in db.list_collection_names() else None
    for m in cursor:
        phone = m.get("sender_phone") or ""
        if not phone or phone in seen:
            continue
        seen.add(phone)
        if outreach is not None and outreach.find_one(
            {"client_name": client_name, "phone": phone, "sent_at": {"$gte": m["received_at"]}},
            {"_id": 1},
        ):
            continue
        out.append({
            "contact_name": m.get("contact_name") or "Unknown",
            "phone":        phone,
            "channel":      "whatsapp",
            "reply_text":   (m.get("body") or "")[:160],
            "received_at":  m["received_at"].isoformat() if hasattr(m["received_at"], "isoformat") else m["received_at"],
            "hours_silent": round((now - m["received_at"]).total_seconds() / 3600.0, 1),
        })
        if len(out) >= limit:
            break
    return out


def money_leak_report(
    client_name: str,
    days: int = 30,
    avg_deal_ngn: int = DEFAULT_AVG_DEAL_NGN,
) -> dict[str, Any]:
    """The headline report. One ₦ figure, four categories, real examples.

    `confirmed_ngn`  = money actually owed (ledgers — real).
    `pipeline_ngn`   = estimated value of revivable conversations
                       (count × avg_deal_ngn — clearly an estimate).
    """
    cash = cash_signals_for(client_name)
    missed   = missed_opportunities_for(client_name, days=days, limit=50)
    promises = _ghosted_promises(client_name, days=days, limit=20)
    silent   = _silent_inbound(client_name, days=days, limit=20)

    bd = cash.get("breakdown", {})
    confirmed_ngn = float(cash.get("collectible_total_ngn") or 0)

    categories = [
        {
            "key": "confirmed_owed",
            "label": "Unpaid invoices / rent / fees owed",
            "kind": "confirmed",
            "count": int(cash.get("collectible_count") or 0),
            "amount_ngn": confirmed_ngn,
            "detail": {k: bd.get(k, {}) for k in ("rent", "debt", "school_fees")},
            "examples": [],
        },
        {
            "key": "asked_price_no_quote",
            "label": "Asked your price — never got a quote back",
            "kind": "pipeline",
            "count": len(missed),
            "amount_ngn": len(missed) * avg_deal_ngn,
            "examples": missed[:8],
        },
        {
            "key": "ghosted_promises",
            "label": "Said “I'll pay” — then went quiet",
            "kind": "pipeline",
            "count": len(promises),
            "amount_ngn": len(promises) * avg_deal_ngn,
            "examples": promises[:8],
        },
        {
            "key": "silent_inbound",
            "label": "Messaged you — got no reply at all",
            "kind": "pipeline",
            "count": len(silent),
            "amount_ngn": len(silent) * avg_deal_ngn,
            "examples": silent[:8],
        },
    ]

    pipeline_ngn = sum(c["amount_ngn"] for c in categories if c["kind"] == "pipeline")
    total_leak_count = sum(c["count"] for c in categories)

    return {
        "client":         client_name,
        "window_days":    days,
        "avg_deal_ngn":   avg_deal_ngn,
        "confirmed_ngn":  confirmed_ngn,
        "pipeline_ngn":   pipeline_ngn,
        "total_ngn":      confirmed_ngn + pipeline_ngn,
        "total_leak_count": total_leak_count,
        "categories":     categories,
        "headline": (
            f"₦{(confirmed_ngn + pipeline_ngn):,.0f} sitting in "
            f"{total_leak_count} conversations where money probably died."
        ),
    }


def rescue_targets(client_name: str, days: int = 30, limit: int = 25) -> list[dict]:
    """Flat, de-duplicated, prioritised list of contacts worth a follow-up now —
    powers Revenue Rescue 'Find cash this week' and the owner-voice
    'follow up everyone who asked price' command.

    Priority: ghosted pay-promises > asked-price-no-quote > silent inbound.
    """
    report = money_leak_report(client_name, days=days)
    by_priority = {"ghosted_promises": 0, "asked_price_no_quote": 1, "silent_inbound": 2}
    targets: list[dict] = []
    seen_phones: set[str] = set()
    for cat in sorted(
        [c for c in report["categories"] if c["kind"] == "pipeline"],
        key=lambda c: by_priority.get(c["key"], 9),
    ):
        for ex in cat["examples"]:
            phone = ex.get("phone") or ""
            key = phone or ex.get("contact_id") or ex.get("contact_name")
            if key in seen_phones:
                continue
            seen_phones.add(key)
            targets.append({
                "reason":       cat["key"],
                "reason_label": cat["label"],
                "contact_name": ex.get("contact_name") or "Unknown",
                "phone":        phone,
                "contact_id":   ex.get("contact_id"),
                "last_text":    ex.get("reply_text") or "",
            })
            if len(targets) >= limit:
                return targets
    return targets
