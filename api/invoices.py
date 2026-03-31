"""
Invoice Collection API — Premium feature (Agency Pro plan).
Clients add invoices, AI sends escalating WhatsApp reminders automatically.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from bson import ObjectId
from tools.invoices import (
    create_invoice, mark_paid, mark_written_off, mark_responded,
    add_note, get_invoice_stats, list_invoices, get_due_reminders,
    record_reminder_sent, InvoiceStatus, REMINDER_SEQUENCE,
    get_invoices,
)

router = APIRouter(prefix="/invoices", tags=["Invoice Collection"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    client_name: str
    debtor_name: str
    debtor_phone: str = Field(..., description="E.164 format: +2348012345678")
    debtor_email: Optional[str] = None
    amount_ngn: float = Field(..., gt=0)
    due_date: datetime
    description: str = ""
    # Optional: override the default reminder schedule
    custom_reminder_days: Optional[list[int]] = Field(
        default=None,
        description="Custom days after due date to send reminders e.g. [0, 5, 10, 20]"
    )
    custom_tones: Optional[list[str]] = Field(
        default=None,
        description="Custom tone per reminder e.g. ['polite', 'firm', 'payment_plan', 'final']"
    )


class NoteAdd(BaseModel):
    note: str


class ManualReminderRequest(BaseModel):
    tone: Optional[str] = "polite"   # polite | firm | payment_plan | final


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/")
async def add_invoice(body: InvoiceCreate):
    """Create a new invoice to be chased."""
    invoice_id = create_invoice(
        client_name=body.client_name,
        debtor_name=body.debtor_name,
        debtor_phone=body.debtor_phone,
        amount_ngn=body.amount_ngn,
        due_date=body.due_date,
        description=body.description,
        debtor_email=body.debtor_email,
    )

    # Store custom schedule if provided
    if body.custom_reminder_days or body.custom_tones:
        update = {}
        if body.custom_reminder_days:
            update["custom_reminder_days"] = body.custom_reminder_days
        if body.custom_tones:
            update["custom_tones"] = body.custom_tones
        get_invoices().update_one({"_id": ObjectId(invoice_id)}, {"$set": update})

    return {"success": True, "invoice_id": invoice_id}


@router.get("/")
async def get_invoices_list(
    client_name: Optional[str] = None,
    status: Optional[str] = None,
):
    return list_invoices(client_name=client_name, status=status)


@router.get("/stats")
async def invoice_stats(client_name: Optional[str] = None):
    return get_invoice_stats(client_name=client_name)


@router.get("/due")
async def due_reminders():
    """Invoices due for their next reminder right now."""
    return get_due_reminders()


@router.post("/{invoice_id}/paid")
async def mark_invoice_paid(invoice_id: str):
    _validate_id(invoice_id)
    ok = mark_paid(invoice_id)
    if not ok:
        raise HTTPException(404, "Invoice not found")
    return {"success": True, "status": InvoiceStatus.PAID}


@router.post("/{invoice_id}/written-off")
async def write_off(invoice_id: str):
    _validate_id(invoice_id)
    ok = mark_written_off(invoice_id)
    if not ok:
        raise HTTPException(404, "Invoice not found")
    return {"success": True, "status": InvoiceStatus.WRITTEN_OFF}


@router.post("/{invoice_id}/responded")
async def debtor_responded(invoice_id: str):
    """Mark that the debtor replied — pauses automatic reminders."""
    _validate_id(invoice_id)
    ok = mark_responded(invoice_id)
    if not ok:
        raise HTTPException(404, "Invoice not found")
    return {"success": True, "status": InvoiceStatus.RESPONDED}


@router.post("/{invoice_id}/note")
async def add_invoice_note(invoice_id: str, body: NoteAdd):
    _validate_id(invoice_id)
    add_note(invoice_id, body.note)
    return {"success": True}


@router.post("/{invoice_id}/remind-now")
async def send_manual_reminder(
    invoice_id: str,
    body: ManualReminderRequest,
    background_tasks: BackgroundTasks,
):
    """Manually trigger a reminder for a specific invoice right now."""
    _validate_id(invoice_id)
    invoice = get_invoices().find_one({"_id": ObjectId(invoice_id)})
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    invoice["id"] = str(invoice["_id"])
    background_tasks.add_task(_send_one_reminder, invoice, body.tone)
    return {"success": True, "message": f"Reminder queued with tone: {body.tone}"}


async def _send_one_reminder(invoice: dict, tone: str):
    from agent import generate_invoice_reminder
    from tools.outreach import send_whatsapp
    from datetime import datetime, timezone
    import structlog
    log = structlog.get_logger()

    due_date = invoice.get("due_date")
    now = datetime.now(timezone.utc)
    days_overdue = (now - due_date).days if due_date else 0

    try:
        message = generate_invoice_reminder(
            client_name=invoice["client_name"],
            debtor_name=invoice["debtor_name"],
            amount_ngn=invoice["amount_ngn"],
            description=invoice.get("description", ""),
            days_overdue=days_overdue,
            tone=tone,
            reminder_count=invoice.get("reminder_count", 0),
        )
        result = await send_whatsapp(phone=invoice["debtor_phone"], message=message)
        if result.get("success", True):
            # Map tone to stage
            tone_stage_map = {
                "polite": InvoiceStatus.REMINDED,
                "firm": InvoiceStatus.FOLLOWED_UP,
                "payment_plan": InvoiceStatus.PLAN_OFFERED,
                "final": InvoiceStatus.FINAL_NOTICE,
            }
            stage = tone_stage_map.get(tone, InvoiceStatus.REMINDED)
            record_reminder_sent(invoice["id"], stage)
            log.info("manual_reminder_sent", debtor=invoice["debtor_name"], tone=tone)
    except Exception as e:
        log.error("manual_reminder_failed", invoice_id=invoice["id"], error=str(e))


def _validate_id(invoice_id: str):
    try:
        ObjectId(invoice_id)
    except Exception:
        raise HTTPException(400, "Invalid invoice ID")
