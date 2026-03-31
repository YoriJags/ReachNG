"""
Invoice collection — AI-powered WhatsApp payment reminders.
Sends escalating messages on behalf of the client until the debt is settled.
Premium feature: Agency Pro plan only.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from database import get_db
from pymongo import ASCENDING, DESCENDING
import structlog

log = structlog.get_logger()


# ─── Status states ────────────────────────────────────────────────────────────

class InvoiceStatus:
    PENDING      = "pending"       # Not yet sent
    REMINDED     = "reminded"      # First reminder sent
    FOLLOWED_UP  = "followed_up"   # Second reminder sent
    PLAN_OFFERED = "plan_offered"  # Payment plan offered
    FINAL_NOTICE = "final_notice"  # Final notice sent
    RESPONDED    = "responded"     # Debtor has replied
    PAID         = "paid"          # Marked as paid
    WRITTEN_OFF  = "written_off"   # Given up


# ─── Reminder sequence ────────────────────────────────────────────────────────

REMINDER_SEQUENCE = [
    {
        "stage": InvoiceStatus.REMINDED,
        "days_after_due": 0,
        "tone": "polite",
        "label": "Due date reminder",
    },
    {
        "stage": InvoiceStatus.FOLLOWED_UP,
        "days_after_due": 7,
        "tone": "firm",
        "label": "7-day follow-up",
    },
    {
        "stage": InvoiceStatus.PLAN_OFFERED,
        "days_after_due": 14,
        "tone": "payment_plan",
        "label": "Payment plan offer",
    },
    {
        "stage": InvoiceStatus.FINAL_NOTICE,
        "days_after_due": 21,
        "tone": "final",
        "label": "Final notice",
    },
]


# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_invoices():
    return get_db()["invoices"]


def ensure_invoice_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_invoices()
    col.create_index([("client_name", ASCENDING)])
    col.create_index([("status", ASCENDING)])
    col.create_index([("due_date", ASCENDING)])
    col.create_index([("next_reminder_at", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def create_invoice(
    client_name: str,
    debtor_name: str,
    debtor_phone: str,
    amount_ngn: float,
    due_date: datetime,
    description: str = "",
    debtor_email: Optional[str] = None,
) -> str:
    """Create a new invoice. Returns the invoice _id."""
    now = datetime.now(timezone.utc)
    result = get_invoices().insert_one({
        "client_name": client_name,
        "debtor_name": debtor_name,
        "debtor_phone": debtor_phone,
        "debtor_email": debtor_email,
        "amount_ngn": amount_ngn,
        "due_date": due_date,
        "description": description,
        "status": InvoiceStatus.PENDING,
        "reminder_count": 0,
        "next_reminder_at": due_date,   # First reminder on the due date
        "last_reminder_at": None,
        "created_at": now,
        "paid_at": None,
        "notes": [],
    })
    log.info("invoice_created", client=client_name, debtor=debtor_name, amount=amount_ngn)
    return str(result.inserted_id)


def mark_paid(invoice_id: str, notes: str = "") -> bool:
    result = get_invoices().update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {
            "status": InvoiceStatus.PAID,
            "paid_at": datetime.now(timezone.utc),
        },
        "$push": {"notes": notes} if notes else {"notes": {"$each": []}},
        },
    )
    return result.modified_count > 0


def mark_written_off(invoice_id: str) -> bool:
    result = get_invoices().update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {"status": InvoiceStatus.WRITTEN_OFF}},
    )
    return result.modified_count > 0


def mark_responded(invoice_id: str) -> bool:
    result = get_invoices().update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {"status": InvoiceStatus.RESPONDED}},
    )
    return result.modified_count > 0


def add_note(invoice_id: str, note: str):
    get_invoices().update_one(
        {"_id": ObjectId(invoice_id)},
        {"$push": {"notes": {"text": note, "at": datetime.now(timezone.utc)}}},
    )


# ─── Reminder scheduling ──────────────────────────────────────────────────────

def get_due_reminders() -> list[dict]:
    """
    Return all invoices that are due for their next reminder right now.
    Excludes paid, written_off, responded.
    """
    now = datetime.now(timezone.utc)
    closed = {InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF, InvoiceStatus.RESPONDED}
    docs = list(get_invoices().find({
        "status": {"$nin": list(closed)},
        "next_reminder_at": {"$lte": now},
    }))
    for d in docs:
        d["id"] = str(d["_id"])
    return docs


def record_reminder_sent(invoice_id: str, stage: str):
    """Update invoice after a reminder is sent. Schedule the next one."""
    now = datetime.now(timezone.utc)

    # Find next stage in sequence
    stages = [s["stage"] for s in REMINDER_SEQUENCE]
    current_index = stages.index(stage) if stage in stages else -1
    next_stage = REMINDER_SEQUENCE[current_index + 1] if current_index + 1 < len(REMINDER_SEQUENCE) else None

    invoice = get_invoices().find_one({"_id": ObjectId(invoice_id)})
    due_date = invoice.get("due_date", now)

    next_reminder_at = None
    if next_stage:
        next_reminder_at = due_date + timedelta(days=next_stage["days_after_due"])

    get_invoices().update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {
            "status": stage,
            "last_reminder_at": now,
            "next_reminder_at": next_reminder_at,
        },
        "$inc": {"reminder_count": 1}},
    )


# ─── Stats ────────────────────────────────────────────────────────────────────

def get_invoice_stats(client_name: Optional[str] = None) -> dict:
    match = {}
    if client_name:
        match["client_name"] = client_name

    col = get_invoices()
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_ngn": {"$sum": "$amount_ngn"},
        }},
    ]
    rows = list(col.aggregate(pipeline))

    stats = {r["_id"]: {"count": r["count"], "total_ngn": r["total_ngn"]} for r in rows}
    total_outstanding = sum(
        v["total_ngn"] for k, v in stats.items()
        if k not in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF)
    )
    total_paid = stats.get(InvoiceStatus.PAID, {}).get("total_ngn", 0)

    return {
        "by_status": stats,
        "total_outstanding_ngn": total_outstanding,
        "total_paid_ngn": total_paid,
        "collection_rate": round((total_paid / (total_paid + total_outstanding)) * 100, 1)
            if (total_paid + total_outstanding) > 0 else 0,
    }


def list_invoices(client_name: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    query = {}
    if client_name:
        query["client_name"] = client_name
    if status:
        query["status"] = status
    docs = list(get_invoices().find(query).sort("due_date", ASCENDING))
    for d in docs:
        d["id"] = str(d.pop("_id"))
        for f in ("due_date", "created_at", "last_reminder_at", "next_reminder_at", "paid_at"):
            if hasattr(d.get(f), "isoformat"):
                d[f] = d[f].isoformat()
    return docs
