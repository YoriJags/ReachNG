"""
WhatsApp Inbound Webhook — receives replies from Unipile.

When a parent/debtor replies to a WhatsApp reminder:
1. Log the message to inbound_messages collection
2. Detect payment claim keywords ("I paid", "done", etc.)
3. If payment claim → mark student/invoice as claimed_paid + auto-reply asking for receipt
4. Link message to student via parent_phone match
"""
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone
from database import get_db
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

PAYMENT_KEYWORDS = [
    "i paid", "i have paid", "already paid", "payment done", "transfer done",
    "sent it", "i've paid", "ive paid", "done", "transferred", "i just paid",
    "payment made", "paid already", "just sent", "i sent",
]

RECEIPT_REQUEST = (
    "Thank you for letting us know! To confirm your payment, please reply with "
    "your transaction reference or a screenshot of your receipt. "
    "Once confirmed, no further reminders will be sent."
)


def _is_payment_claim(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in PAYMENT_KEYWORDS)


def _db():
    return get_db()


@router.post("/whatsapp")
async def whatsapp_inbound(request: Request):
    """
    Unipile calls this endpoint for every inbound WhatsApp message.
    No Basic Auth — Unipile must be able to POST freely.
    Secure via: only called from Unipile IPs, payload logged regardless.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    # Unipile payload shape
    data = payload.get("data", {})
    sender_phone = data.get("from") or payload.get("from")
    message_body = data.get("body") or data.get("text") or payload.get("body", "")
    account_id = data.get("account_id") or payload.get("account_id")
    event = payload.get("event", "message.received")

    if not sender_phone:
        log.warning("inbound_webhook_no_sender", payload=payload)
        return {"ok": True}  # Always 200 to Unipile — never retry on our logic errors

    now = datetime.now(timezone.utc)
    is_claim = _is_payment_claim(message_body)

    # Log every inbound message
    log_doc = {
        "sender_phone": sender_phone,
        "body": message_body,
        "account_id": account_id,
        "event": event,
        "is_payment_claim": is_claim,
        "received_at": now,
        "linked_student_id": None,
        "linked_product": None,
    }

    # Try to link to a School Fees student
    student = _db()["sf_students"].find_one({"parent_phone": sender_phone, "active": True, "paid": False})
    if student:
        log_doc["linked_student_id"] = str(student["_id"])
        log_doc["linked_product"] = "school_fees"

        if is_claim:
            from bson import ObjectId
            _db()["sf_students"].update_one(
                {"_id": student["_id"]},
                {"$set": {"claimed_paid": True, "claim_received_at": now}},
            )
            log.info("payment_claim_received", product="school_fees", student=student.get("student_name"), phone=sender_phone)

            # Auto-reply from the school's WhatsApp
            school = _db()["sf_schools"].find_one({"_id": ObjectId(student["school_id"])}) if student.get("school_id") else None
            if school:
                try:
                    from tools.outreach import send_whatsapp_for_client
                    await send_whatsapp_for_client(
                        phone=sender_phone,
                        message=RECEIPT_REQUEST,
                        client_doc=school,
                    )
                    log_doc["auto_reply_sent"] = True
                except Exception as e:
                    log.warning("auto_reply_failed", error=str(e))
                    log_doc["auto_reply_sent"] = False

    # Try to link to Invoice Chaser (most recent unpaid invoice for this debtor)
    if not log_doc["linked_student_id"]:
        invoice = _db()["chased_invoices"].find_one(
            {"debtor_phone": sender_phone, "status": "sent"},
            sort=[("sent_at", -1)],
        )
        if invoice:
            log_doc["linked_product"] = "invoice_chaser"
            log_doc["linked_invoice_id"] = str(invoice["_id"])
            if is_claim:
                _db()["chased_invoices"].update_one(
                    {"_id": invoice["_id"]},
                    {"$set": {"claimed_paid": True, "claim_received_at": now}},
                )
                log.info("payment_claim_received", product="invoice_chaser", phone=sender_phone)

    _db()["inbound_messages"].insert_one(log_doc)
    return {"ok": True}


@router.get("/inbound-messages")
async def list_inbound(limit: int = 50, product: str = None):
    """List recent inbound messages — for dashboard inbox view."""
    query = {}
    if product:
        query["linked_product"] = product
    msgs = list(
        _db()["inbound_messages"]
        .find(query)
        .sort("received_at", -1)
        .limit(min(limit, 200))
    )
    for m in msgs:
        m["_id"] = str(m["_id"])
        if isinstance(m.get("received_at"), datetime):
            m["received_at"] = m["received_at"].isoformat()
    return {"messages": msgs, "total": len(msgs)}
