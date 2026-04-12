"""
WhatsApp Inbound Webhook — handles replies from both Unipile and Meta Cloud API.

Supports two inbound sources simultaneously:
- Unipile: POST with {event, data: {from, body, account_id}}
- Meta:    GET  for verification challenge + POST with {object, entry[].changes[].value.messages[]}

When a parent/debtor replies:
1. Parse sender + message from whichever source delivered it
2. Log to inbound_messages collection
3. Detect payment claim keywords ("I paid", "done", etc.)
4. If claim → mark student/invoice as claimed_paid + auto-reply asking for receipt
5. If source unavailable → return null-safe response, never crash
"""
from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
from datetime import datetime, timezone
from database import get_db
from config import get_settings
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
    lower = (text or "").lower().strip()
    return any(kw in lower for kw in PAYMENT_KEYWORDS)


def _db():
    return get_db()


def _parse_unipile(payload: dict) -> tuple[str | None, str, str | None]:
    """Extract (sender_phone, message_body, account_id) from a Unipile payload."""
    data = payload.get("data", {})
    sender = data.get("from") or payload.get("from")
    body = data.get("body") or data.get("text") or payload.get("body", "")
    account_id = data.get("account_id") or payload.get("account_id")
    return sender, body, account_id


def _parse_meta(payload: dict) -> list[tuple[str | None, str]]:
    """
    Extract list of (sender_phone, message_body) from a Meta Cloud API payload.
    Meta batches messages so we return a list.
    """
    results = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    sender = msg.get("from")
                    body = (msg.get("text") or {}).get("body", "")
                    if sender:
                        results.append((sender, body))
    except Exception as e:
        log.warning("meta_payload_parse_error", error=str(e))
    return results


# ─── Meta verification handshake ──────────────────────────────────────────────

@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """
    Meta sends a GET to verify the webhook URL before activating it.
    Must echo back hub.challenge if hub.verify_token matches our secret.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    settings = get_settings()
    if mode == "subscribe" and token == settings.webhook_verify_token:
        log.info("meta_webhook_verified")
        return PlainTextResponse(challenge or "")

    log.warning("meta_webhook_verify_failed", token=token)
    return Response(status_code=403)


# ─── Inbound message handler ───────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_inbound(request: Request):
    """
    Handles inbound WhatsApp messages from both Unipile and Meta.
    Always returns 200 — never let delivery failures trigger retries from either provider.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}  # Malformed payload — ack and move on

    # Detect source and extract messages
    messages_to_process: list[tuple[str | None, str, str | None]] = []

    if payload.get("object") == "whatsapp_business_account":
        # Meta Cloud API payload
        for sender, body in _parse_meta(payload):
            messages_to_process.append((sender, body, "meta"))
    else:
        # Unipile payload
        sender, body, account_id = _parse_unipile(payload)
        messages_to_process.append((sender, body, account_id))

    for sender_phone, message_body, source in messages_to_process:
        if not sender_phone:
            continue
        await _handle_message(sender_phone, message_body, source, payload.get("event", "message.received"))

    return {"ok": True}


async def _handle_message(sender_phone: str, message_body: str, source: str | None, event: str):
    """Process a single inbound message — link, classify, auto-reply, log."""
    now = datetime.now(timezone.utc)
    is_claim = _is_payment_claim(message_body)

    log_doc = {
        "sender_phone": sender_phone,
        "body": message_body,
        "source": source,
        "event": event,
        "is_payment_claim": is_claim,
        "received_at": now,
        "linked_student_id": None,
        "linked_product": None,
        "auto_reply_sent": False,
    }

    try:
        # ── Link to School Fees student ────────────────────────────────────────
        student = _db()["sf_students"].find_one({"parent_phone": sender_phone, "active": True, "paid": False})
        if student:
            log_doc["linked_student_id"] = str(student["_id"])
            log_doc["linked_product"] = "school_fees"

            if is_claim:
                _db()["sf_students"].update_one(
                    {"_id": student["_id"]},
                    {"$set": {"claimed_paid": True, "claim_received_at": now}},
                )
                log.info("payment_claim_received", product="school_fees", student=student.get("student_name"), phone=sender_phone)

                # Auto-reply from the school's WhatsApp (Unipile or Meta — same router)
                try:
                    from bson import ObjectId
                    from tools.outreach import send_whatsapp_for_client
                    school = _db()["sf_schools"].find_one({"_id": ObjectId(student["school_id"])}) if student.get("school_id") else None
                    await send_whatsapp_for_client(
                        phone=sender_phone,
                        message=RECEIPT_REQUEST,
                        client_doc=school,
                    )
                    log_doc["auto_reply_sent"] = True
                except Exception as e:
                    log.warning("auto_reply_failed", error=str(e))

        # ── Link to Invoice Chaser ─────────────────────────────────────────────
        elif not log_doc["linked_student_id"]:
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

    except Exception as e:
        log.error("inbound_message_processing_error", error=str(e), phone=sender_phone)
        # Still log the raw message even if processing failed
        log_doc["processing_error"] = str(e)

    try:
        _db()["inbound_messages"].insert_one(log_doc)
    except Exception as e:
        log.error("inbound_message_log_failed", error=str(e))


# ─── Dashboard inbox ───────────────────────────────────────────────────────────

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
