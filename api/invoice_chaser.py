"""
Invoice Chaser — upload a PDF invoice, extract fields via Gemini Flash,
send automated WhatsApp payment reminders via Unipile.
Tier 1 product built on ReachNG infrastructure.
"""
import pathlib
from datetime import datetime, date
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from agent.brain import extract_invoice_fields, generate_invoice_reminder
from tools.messaging import send_whatsapp
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/invoice-chaser", tags=["Invoice Chaser"])

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InvoiceReminderRequest(BaseModel):
    client_name: str = Field(..., max_length=200)
    debtor_phone: str = Field(..., max_length=20)   # +234XXXXXXXXXX
    debtor_name: str = Field(..., max_length=200)
    amount_ngn: float = Field(..., gt=0)
    description: str = Field(default="Services rendered", max_length=500)
    days_overdue: int = Field(default=0, ge=0)
    reminder_count: int = Field(default=0, ge=0)    # 0=first, 1=second, 2=final


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pick_tone(days_overdue: int, reminder_count: int) -> str:
    if reminder_count == 0:
        return "polite"
    if reminder_count == 1 or days_overdue < 14:
        return "firm"
    if reminder_count == 2 or days_overdue < 30:
        return "payment_plan"
    return "final"


def _store_invoice(data: dict) -> str:
    db = get_db()
    result = db["chased_invoices"].insert_one(data)
    return str(result.inserted_id)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/parse")
async def parse_invoice(file: UploadFile = File(...)):
    """
    Upload a PDF invoice → Gemini Flash extracts debtor name, amount, description, due date.
    Returns extracted fields for review before sending reminders.
    """
    if not file.filename:
        raise HTTPException(400, "Filename required.")

    safe_name = pathlib.Path(file.filename).name
    if pathlib.Path(safe_name).suffix.lower() != ".pdf":
        raise HTTPException(400, "Only PDF files accepted.")

    content = await file.read()
    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(413, "File too large. Max 10MB.")

    # Extract text from PDF
    try:
        import pymupdf  # pip install pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except ImportError:
        raise HTTPException(500, "PDF parsing not available. Run: pip install pymupdf")
    except Exception as e:
        raise HTTPException(422, f"Could not read PDF: {e}")

    if not text.strip():
        raise HTTPException(422, "PDF appears to be a scanned image. Text extraction failed.")

    fields = extract_invoice_fields(text)

    return {
        "filename": safe_name,
        "extracted": fields,
        "raw_text_preview": text[:300] + "..." if len(text) > 300 else text,
    }


@router.post("/send-reminder")
async def send_reminder(req: InvoiceReminderRequest):
    """
    Send a WhatsApp payment reminder for an invoice.
    Tone escalates automatically based on days_overdue + reminder_count.
    """
    tone = _pick_tone(req.days_overdue, req.reminder_count)

    message = generate_invoice_reminder(
        client_name=req.client_name,
        debtor_name=req.debtor_name,
        amount_ngn=req.amount_ngn,
        description=req.description,
        days_overdue=req.days_overdue,
        tone=tone,
        reminder_count=req.reminder_count,
    )

    # Send via Unipile
    try:
        await send_whatsapp(
            to=req.debtor_phone,
            message=message,
            account_id=None,  # uses default account
        )
        status = "sent"
    except Exception as e:
        log.error("invoice_reminder_send_failed", error=str(e), phone=req.debtor_phone)
        status = "failed"

    # Store record
    record = {
        "client_name": req.client_name,
        "debtor_name": req.debtor_name,
        "debtor_phone": req.debtor_phone,
        "amount_ngn": req.amount_ngn,
        "description": req.description,
        "days_overdue": req.days_overdue,
        "reminder_count": req.reminder_count,
        "tone": tone,
        "message": message,
        "status": status,
        "sent_at": datetime.utcnow(),
    }
    _store_invoice(record)

    return {
        "status": status,
        "tone_used": tone,
        "message_preview": message[:100] + "..." if len(message) > 100 else message,
        "reminder_count": req.reminder_count,
    }


@router.get("/history/{client_name}")
async def get_history(client_name: str, limit: int = 50):
    """List all chased invoices for a client."""
    db = get_db()
    import re
    docs = list(
        db["chased_invoices"]
        .find({"client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}})
        .sort("sent_at", -1)
        .limit(min(limit, 100))
    )
    for d in docs:
        d["_id"] = str(d["_id"])
        if isinstance(d.get("sent_at"), datetime):
            d["sent_at"] = d["sent_at"].isoformat()
    return {"client_name": client_name, "invoices": docs, "total": len(docs)}
