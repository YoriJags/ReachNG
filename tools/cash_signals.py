"""
Cash signals aggregator for the Owner Brief.

Pulls money-focused numbers per client across the four cash workflows:
  - Recover Money: debt_cases, estate_rent_ledger, sf_students
  - Activate Leads: replies (interested), pending_approvals (asked-price)
  - Close Deals: pending_approvals (actions today), confirmed bookings
  - Retain: not yet aggregated here

KPI #4: ₦ recovered + ₦ in qualified pipeline — this is the headline.

Conservative joins:
  - estate_rent_ledger.landlord_company == client_name
  - sf_schools.name == client_name (so we can look up student fees)
  - debt_cases.client_name == client_name
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from database import get_db


_LAGOS = timedelta(hours=1)


def _safe_sum(cursor, field: str = "amount_ngn") -> float:
    total = 0.0
    for d in cursor:
        v = d.get(field)
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def _overdue_rent_total(client_name: str) -> tuple[float, int]:
    """₦ + count of open rent charges past due, scoped to landlord_company."""
    db = get_db()
    if "estate_rent_ledger" not in db.list_collection_names():
        return 0.0, 0
    now = datetime.now(timezone.utc)
    match = {
        "status": "open",
        "due_date": {"$lt": now},
        "landlord_company": client_name,
    }
    docs = list(db["estate_rent_ledger"].find(match, {"amount_ngn": 1, "paid_amount": 1}))
    total = 0.0
    for d in docs:
        amt  = float(d.get("amount_ngn") or 0)
        paid = float(d.get("paid_amount") or 0)
        total += max(0.0, amt - paid)
    return total, len(docs)


def _active_debt_total(client_name: str) -> tuple[float, int]:
    db = get_db()
    if "debt_cases" not in db.list_collection_names():
        return 0.0, 0
    docs = list(db["debt_cases"].find(
        {"status": "active", "client_name": client_name},
        {"amount_ngn": 1},
    ))
    return _safe_sum(docs), len(docs)


def _unpaid_fees_total(client_name: str) -> tuple[float, int]:
    """For schools — sum fee_amount where paid=False, joined via sf_schools.name."""
    db = get_db()
    if "sf_schools" not in db.list_collection_names():
        return 0.0, 0
    school = db["sf_schools"].find_one({"name": client_name}, {"_id": 1})
    if not school:
        return 0.0, 0
    school_id = str(school["_id"])
    docs = list(db["sf_students"].find(
        {"school_id": school_id, "paid": False, "active": True},
        {"fee_amount": 1},
    ))
    total = sum(float(d.get("fee_amount") or 0) for d in docs)
    return total, len(docs)


def _cash_received_overnight(client_name: str, since: datetime) -> float:
    db = get_db()
    received = 0.0
    if "debt_cases" in db.list_collection_names():
        for d in db["debt_cases"].find(
            {"client_name": client_name, "status": "paid", "paid_at": {"$gte": since}},
            {"amount_ngn": 1},
        ):
            received += float(d.get("amount_ngn") or 0)
    if "sf_schools" in db.list_collection_names():
        school = db["sf_schools"].find_one({"name": client_name}, {"_id": 1})
        if school and "sf_payments" in db.list_collection_names():
            student_ids = [
                str(s["_id"]) for s in db["sf_students"].find(
                    {"school_id": str(school["_id"])}, {"_id": 1}
                )
            ]
            if student_ids:
                for p in db["sf_payments"].find(
                    {"student_id": {"$in": student_ids}, "paid_at": {"$gte": since}},
                    {"amount_paid": 1},
                ):
                    received += float(p.get("amount_paid") or 0)
    return received


def _hot_replies(client_name: str, since: datetime) -> int:
    db = get_db()
    if "replies" not in db.list_collection_names():
        return 0
    return db["replies"].count_documents({
        "client_name": client_name,
        "received_at": {"$gte": since},
        "intent": "interested",
    })


_PRICE_TOKENS = (
    "how much", "price", "pricing", "rate", "rates", "cost", "costs", "fee", "fees",
    "quote", "tariff", "package", "packages", "naira", "₦", "ngn",
    "send me your", "send your", "drop your price",
)


def _looks_like_price_ask(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(tok in t for tok in _PRICE_TOKENS)


def missed_opportunities_for(
    client_name: str,
    days: int = 30,
    grace_hours: int = 6,
    limit: int = 20,
) -> list[dict]:
    """
    Missed Opportunity Radar — leads who asked for price but never got a quote.

    Detection:
      1. Find replies in last `days` whose body looks like a price ask.
      2. Resolve contact_id → client_name (via contacts.client_name).
      3. Filter to this client.
      4. Mark missed if no outreach_log entry to that contact since the reply
         (with `grace_hours` window so a same-hour follow-up doesn't count
         as missed yet).

    Returns a list of {contact_id, contact_name, channel, reply_text,
    reply_at, hours_since_ask}.
    """
    db = get_db()
    if "replies" not in db.list_collection_names():
        return []

    since = datetime.now(timezone.utc) - timedelta(days=days)
    contacts_col = db["contacts"]
    outreach_col = db["outreach_log"] if "outreach_log" in db.list_collection_names() else None

    cursor = db["replies"].find(
        {"received_at": {"$gte": since}},
        {"text": 1, "summary": 1, "contact_id": 1, "contact_name": 1, "channel": 1, "received_at": 1},
    ).sort("received_at", -1).limit(500)

    out: list[dict] = []
    now = datetime.now(timezone.utc)

    for r in cursor:
        body = (r.get("text") or "") + " " + (r.get("summary") or "")
        if not _looks_like_price_ask(body):
            continue
        cid = r.get("contact_id")
        if not cid:
            continue
        contact = contacts_col.find_one(
            {"_id": cid},
            {"client_name": 1, "name": 1, "phone": 1, "vertical": 1},
        )
        if not contact or contact.get("client_name") != client_name:
            continue

        reply_at = r["received_at"]
        cutoff = reply_at + timedelta(hours=grace_hours)
        if outreach_col is not None and outreach_col.find_one(
            {"contact_id": cid, "sent_at": {"$gte": cutoff}}, {"_id": 1}
        ):
            continue  # we did follow up

        hours = max(0.0, (now - reply_at).total_seconds() / 3600.0)
        out.append({
            "contact_id":   str(cid),
            "contact_name": contact.get("name") or r.get("contact_name") or "",
            "phone":        contact.get("phone") or "",
            "channel":      r.get("channel") or "",
            "reply_text":   (r.get("text") or "")[:200],
            "reply_at":     reply_at.isoformat(),
            "hours_since":  round(hours, 1),
        })
        if len(out) >= limit:
            break
    return out


def _asked_price_no_quote(client_name: str) -> int:
    """Missed Opportunity Radar count — uses the radar list above."""
    return len(missed_opportunities_for(client_name, limit=999))


def cash_signals_for(client_name: str, hours: int = 14) -> dict[str, Any]:
    """
    Returns the cash-focused signal pack for one client's morning brief.

    Numbers compose into the Owner Brief headline:
      "You have ₦X likely collectible. Y hot leads. Z actions today.
       ₦W landed overnight."
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rent_amt,  rent_cnt  = _overdue_rent_total(client_name)
    debt_amt,  debt_cnt  = _active_debt_total(client_name)
    fees_amt,  fees_cnt  = _unpaid_fees_total(client_name)
    received             = _cash_received_overnight(client_name, since)
    hot                  = _hot_replies(client_name, since)
    price_asked          = _asked_price_no_quote(client_name)

    collectible_total = rent_amt + debt_amt + fees_amt
    collectible_count = rent_cnt + debt_cnt + fees_cnt

    return {
        "collectible_total_ngn":  collectible_total,
        "collectible_count":      collectible_count,
        "breakdown": {
            "rent":          {"amount_ngn": rent_amt,  "count": rent_cnt},
            "debt":          {"amount_ngn": debt_amt,  "count": debt_cnt},
            "school_fees":   {"amount_ngn": fees_amt,  "count": fees_cnt},
        },
        "cash_received_overnight_ngn": received,
        "hot_replies_overnight":       hot,
        "asked_price_no_quote":        price_asked,
    }
