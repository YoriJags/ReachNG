"""
WhatsApp Inbound Webhook — handles replies from both Unipile and Meta Cloud API.

SECURITY: every POST is signature-validated before parsing or message handling.
- Meta: X-Hub-Signature-256 header verified via HMAC-SHA256 with META_APP_SECRET.
- Unipile: Unipile-Auth header matched against UNIPILE_WEBHOOK_SECRET.
- Set WEBHOOK_DEV_BYPASS=true for local development only.

Flow for every inbound message:
1. Validate signature (reject 401 on failure in production)
2. Parse sender + body from Unipile or Meta payload
3. Link to a student (school fees) or invoice (invoice chaser) by phone number
4. Claude classifies the reply + generates a context-aware auto-reply
5. Auto-reply sent back to debtor on WhatsApp
6. Bursar/client forwarded a one-line notification on their WhatsApp
7. Everything logged to inbound_messages collection
"""
import hmac
import hashlib
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from datetime import datetime, timezone
from database import get_db
from config import get_settings
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _db():
    return get_db()


async def _maybe_send_holding_reply(client: dict, sender_phone: str) -> bool:
    """Fire client.holding_message instantly if:
      - autopilot is OFF (when ON, AI replies fast — no need)
      - holding_message is set (non-empty)
      - last holding reply to THIS contact was >24h ago (or never)

    Returns True if a holding reply was sent.
    """
    if client.get("autopilot"):
        return False
    msg = (client.get("holding_message") or "").strip()
    if not msg:
        return False

    holding_log = _db()["holding_replies_sent"]
    cutoff = datetime.now(timezone.utc).timestamp() - 24 * 3600
    recent = holding_log.find_one({
        "client_id": str(client["_id"]),
        "phone": sender_phone,
        "sent_at": {"$gte": datetime.fromtimestamp(cutoff, tz=timezone.utc)},
    })
    if recent:
        return False

    try:
        from tools.outreach import send_whatsapp_for_client
        await send_whatsapp_for_client(
            phone=sender_phone,
            message=msg,
            client_doc=client,
        )
        holding_log.insert_one({
            "client_id": str(client["_id"]),
            "client_name": client["name"],
            "phone": sender_phone,
            "sent_at": datetime.now(timezone.utc),
        })
        log.info("holding_reply_sent", client=client["name"])
        return True
    except Exception as e:
        log.warning("holding_reply_failed", client=client.get("name"), error=str(e))
        return False


def _parse_unipile(payload: dict) -> tuple[str | None, str, str | None]:
    data = payload.get("data", {})
    sender = data.get("from") or payload.get("from")
    body = data.get("body") or data.get("text") or payload.get("body", "")
    account_id = data.get("account_id") or payload.get("account_id")
    return sender, body, account_id


def _parse_meta(payload: dict) -> list[tuple[str, str]]:
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


# ─── Signature validation ────────────────────────────────────────────────────

def _is_meta_payload_shape(headers: dict, body_bytes: bytes) -> bool:
    """Heuristic — Meta posts always include x-hub-signature-256 (or fail-closed for prod)."""
    return "x-hub-signature-256" in {k.lower() for k in headers.keys()}


def _verify_meta_signature(body: bytes, sig_header: str, app_secret: str) -> bool:
    """Validate Meta's x-hub-signature-256 header (sha256=<hex>) against HMAC-SHA256(body, app_secret)."""
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = sig_header.split("=", 1)[1].strip()
    return hmac.compare_digest(received, expected)


def _verify_unipile_signature(unipile_auth_header: str, secret: str) -> bool:
    """Unipile's webhook auth — exact-match the configured secret in the Unipile-Auth header."""
    if not unipile_auth_header or not secret:
        return False
    return hmac.compare_digest(unipile_auth_header.strip(), secret.strip())


async def _validate_webhook_request(request: Request) -> bytes:
    """Verify webhook authenticity. Returns raw body bytes if valid; raises 401 otherwise.

    Resolution order:
      1. Dev bypass (WEBHOOK_DEV_BYPASS=true) — skip checks. Local only.
      2. Meta signature header present → require META_APP_SECRET match.
      3. Unipile-Auth header present → require UNIPILE_WEBHOOK_SECRET match.
      4. Neither header present → reject (production) or warn (development).
    """
    settings = get_settings()
    body = await request.body()

    if settings.webhook_dev_bypass:
        log.warning("webhook_signature_bypassed", reason="WEBHOOK_DEV_BYPASS=true")
        return body

    headers = {k.lower(): v for k, v in request.headers.items()}
    is_production = (settings.app_env or "").lower() in ("production", "prod", "live")

    meta_sig = headers.get("x-hub-signature-256")
    unipile_auth = headers.get("unipile-auth") or headers.get("x-unipile-auth")

    # Path 1 — Meta inbound
    if meta_sig:
        if not settings.meta_app_secret:
            log.error("meta_webhook_secret_missing")
            if is_production:
                raise HTTPException(503, "Meta webhook secret not configured")
            return body
        if _verify_meta_signature(body, meta_sig, settings.meta_app_secret):
            return body
        log.warning("meta_webhook_signature_invalid")
        raise HTTPException(401, "Invalid Meta signature")

    # Path 2 — Unipile inbound
    if unipile_auth:
        if not settings.unipile_webhook_secret:
            log.error("unipile_webhook_secret_missing")
            if is_production:
                raise HTTPException(503, "Unipile webhook secret not configured")
            return body
        if _verify_unipile_signature(unipile_auth, settings.unipile_webhook_secret):
            return body
        log.warning("unipile_webhook_signature_invalid")
        raise HTTPException(401, "Invalid Unipile signature")

    # Path 3 — no recognized signature header
    if is_production:
        log.warning("webhook_unsigned_post_rejected")
        raise HTTPException(401, "Webhook signature missing")
    log.warning("webhook_unsigned_dev_allowed")
    return body


# ─── Meta verification handshake ──────────────────────────────────────────────

@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
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
    Handles inbound WhatsApp replies from Unipile or Meta.
    Always returns 200 to legit senders — never retry-loops from either provider.

    Signature-validated: invalid Meta x-hub-signature-256 or wrong Unipile-Auth
    header → 401. Unsigned POSTs → 401 in production, allowed in development
    with a warning. Set WEBHOOK_DEV_BYPASS=true to skip checks entirely (local
    only — never set in production).
    """
    import json as _json
    body_bytes = await _validate_webhook_request(request)
    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except Exception:
        return {"ok": True}

    messages_to_process: list[tuple[str | None, str, str | None]] = []

    if payload.get("object") == "whatsapp_business_account":
        for sender, body in _parse_meta(payload):
            messages_to_process.append((sender, body, "meta"))
    else:
        sender, body, account_id = _parse_unipile(payload)
        messages_to_process.append((sender, body, account_id))

    for sender_phone, message_body, source in messages_to_process:
        if not sender_phone:
            continue
        try:
            await _handle_message(sender_phone, message_body, source, payload.get("event", "message.received"))
        except Exception as e:
            log.error("inbound_handler_crashed", error=str(e), phone=sender_phone)

    return {"ok": True}


async def _handle_message(sender_phone: str, message_body: str, source: str | None, event: str):
    """
    Full pipeline for one inbound message:
    link → classify via Claude → auto-reply to debtor → notify bursar → log

    Closer intake (Phase 1): if `source` matches a client's `whatsapp_account_id`
    AND that client has `closer_enabled=True` AND `vertical=real_estate`, route
    the inbound to the Closer lead thread. No AI reply yet — Phase 2 adds drafting.
    """
    from tools.outreach import send_whatsapp_for_client

    now = datetime.now(timezone.utc)

    log_doc = {
        "sender_phone": sender_phone,
        "body": message_body,
        "source": source,
        "event": event,
        "received_at": now,
        "linked_product": None,
        "intent": None,
        "claimed_paid": False,
        "auto_reply_sent": False,
        "bursar_notified": False,
    }

    # ── Holding Reply — universal across all verticals ────────────────────────
    # Fire instantly for any active client whose WhatsApp line received this
    # inbound, regardless of vertical or product wired underneath. Gated by
    # autopilot=OFF + holding_message set + 24h dedupe per contact.
    matched_client = None
    try:
        if source and source not in ("meta",):
            matched_client = _db()["clients"].find_one({
                "whatsapp_account_id": source,
                "active": True,
            })
            if matched_client:
                await _maybe_send_holding_reply(matched_client, sender_phone)
    except Exception as e:
        log.warning("holding_reply_lookup_failed", error=str(e))

    # ── Closer intake (any vertical with closer_enabled) ───────────────────────
    # Closer is now universal — the Business Brief drives persona, not the vertical.
    # Any active client with closer_enabled gets inbound routed to the lead thread.
    try:
        if matched_client and matched_client.get("closer_enabled"):
            closer_client = matched_client
            if closer_client:
                from services.closer import find_lead_by_contact, create_lead, append_thread_message
                client_id = str(closer_client["_id"])
                existing = find_lead_by_contact(client_id, phone=sender_phone)
                if existing:
                    lead_id = str(existing["_id"])
                    append_thread_message(
                        lead_id,
                        direction="in",
                        channel="whatsapp",
                        body=message_body,
                    )
                    log_doc["linked_product"] = "closer"
                    log_doc["linked_lead_id"] = lead_id
                    # Auto-draft the next move — queues to HITL, never auto-sends.
                    try:
                        from services.closer.brain import draft_next_move
                        draft_next_move(lead_id)
                    except Exception as _e:
                        log.warning("closer_autodraft_failed", lead=lead_id, error=str(_e))
                else:
                    lead = create_lead(
                        client_id=client_id,
                        client_name=closer_client["name"],
                        vertical=closer_client.get("vertical") or "general",
                        source="whatsapp",
                        contact_phone=sender_phone,
                        inquiry_text=message_body,
                        source_consent="inbound",
                    )
                    log_doc["linked_product"] = "closer"
                    log_doc["linked_lead_id"] = lead["id"]
                    # First-touch auto-draft on the new lead — owner approves to send.
                    try:
                        from services.closer.brain import draft_next_move
                        draft_next_move(lead["id"])
                    except Exception as _e:
                        log.warning("closer_autodraft_first_failed", lead=lead["id"], error=str(_e))
                try:
                    _db()["inbound_messages"].insert_one(log_doc)
                except Exception:
                    pass
                return
    except Exception as e:
        log.error("closer_intake_failed", error=str(e), phone=sender_phone)

    # ── Try to link to Rent Roll tenant ───────────────────────────────────────
    tenant = _db()["estate_tenants"].find_one({
        "phone": sender_phone,
        "status": "active",
    })
    if tenant:
        log_doc["linked_product"] = "rent_roll"
        log_doc["linked_tenant_id"] = str(tenant["_id"])
        try:
            from bson import ObjectId
            from agent.brain import handle_payment_reply

            open_charge = _db()["estate_rent_ledger"].find_one(
                {"tenant_id": str(tenant["_id"]), "status": "open"},
                sort=[("due_date", 1)],
            )
            if open_charge:
                unit = _db()["estate_units"].find_one({"_id": ObjectId(open_charge["unit_id"])})
                result = handle_payment_reply(
                    reply_text=message_body,
                    debtor_name=tenant.get("tenant_name", "Tenant"),
                    amount_ngn=open_charge.get("amount_ngn", 0),
                    due_date=open_charge.get("due_date", ""),
                    product="rent_roll",
                )
                log_doc["intent"] = result.get("intent")
                log_doc["claimed_paid"] = result.get("claimed_paid", False)
                if result.get("claimed_paid"):
                    _db()["estate_rent_ledger"].update_one(
                        {"_id": open_charge["_id"]},
                        {"$set": {"claimed_paid": True, "claim_received_at": now}},
                    )
                auto_reply = result.get("auto_reply", "")
                if auto_reply:
                    try:
                        await send_whatsapp_for_client(phone=sender_phone, message=auto_reply)
                        log_doc["auto_reply_sent"] = True
                    except Exception as e:
                        log.warning("auto_reply_failed", error=str(e))
                landlord_phone = (unit or {}).get("landlord_phone", "")
                if landlord_phone and result.get("notify_bursar"):
                    try:
                        await send_whatsapp_for_client(
                            phone=landlord_phone,
                            message=f"[ReachNG] {result['notify_bursar']}",
                        )
                        log_doc["bursar_notified"] = True
                    except Exception as e:
                        log.warning("landlord_notify_failed", error=str(e))
        except Exception as e:
            log.error("rent_roll_reply_processing_failed", error=str(e), phone=sender_phone)
            log_doc["processing_error"] = str(e)

        try:
            _db()["inbound_messages"].insert_one(log_doc)
        except Exception:
            pass
        return

    # ── Try to link to School Fees student ────────────────────────────────────
    student = _db()["sf_students"].find_one({
        "parent_phone": sender_phone,
        "active": True,
        "paid": False,
    })

    if student:
        log_doc["linked_product"] = "school_fees"
        log_doc["linked_student_id"] = str(student["_id"])

        try:
            from bson import ObjectId
            from agent.brain import handle_payment_reply

            school = _db()["sf_schools"].find_one({"_id": ObjectId(student["school_id"])}) if student.get("school_id") else None
            balance = max(0, student["fee_amount"] - student.get("amount_paid", 0))

            result = handle_payment_reply(
                reply_text=message_body,
                debtor_name=student.get("parent_name", "Parent"),
                amount_ngn=balance,
                due_date=student.get("due_date", ""),
                product="school_fees",
            )

            log_doc["intent"] = result.get("intent")
            log_doc["claimed_paid"] = result.get("claimed_paid", False)

            # Update student if payment claimed
            if result.get("claimed_paid"):
                _db()["sf_students"].update_one(
                    {"_id": student["_id"]},
                    {"$set": {"claimed_paid": True, "claim_received_at": now}},
                )
                log.info("payment_claim_received", product="school_fees",
                         student=student.get("student_name"), phone=sender_phone)

            # Auto-reply to parent
            auto_reply = result.get("auto_reply", "")
            if auto_reply and school:
                try:
                    await send_whatsapp_for_client(
                        phone=sender_phone,
                        message=auto_reply,
                        client_doc=school,
                    )
                    log_doc["auto_reply_sent"] = True
                except Exception as e:
                    log.warning("auto_reply_failed", error=str(e))

            # Forward to bursar
            bursar_summary = result.get("notify_bursar", "")
            bursar_phone = school.get("contact_phone") if school else None
            if bursar_summary and bursar_phone and school:
                bursar_msg = f"[ReachNG] {bursar_summary}"
                try:
                    await send_whatsapp_for_client(
                        phone=bursar_phone,
                        message=bursar_msg,
                        client_doc=school,
                    )
                    log_doc["bursar_notified"] = True
                except Exception as e:
                    log.warning("bursar_notify_failed", error=str(e))

        except Exception as e:
            log.error("school_fees_reply_processing_failed", error=str(e), phone=sender_phone)
            log_doc["processing_error"] = str(e)

    # ── Try to link to Invoice Chaser ─────────────────────────────────────────
    else:
        invoice = _db()["chased_invoices"].find_one(
            {"debtor_phone": sender_phone, "status": "sent"},
            sort=[("sent_at", -1)],
        )
        if invoice:
            log_doc["linked_product"] = "invoice_chaser"
            log_doc["linked_invoice_id"] = str(invoice["_id"])

            try:
                from agent.brain import handle_payment_reply

                result = handle_payment_reply(
                    reply_text=message_body,
                    debtor_name=invoice.get("debtor_name", "Debtor"),
                    amount_ngn=invoice.get("amount_ngn", 0),
                    due_date="",
                    product="invoice_chaser",
                )

                log_doc["intent"] = result.get("intent")
                log_doc["claimed_paid"] = result.get("claimed_paid", False)

                if result.get("claimed_paid"):
                    _db()["chased_invoices"].update_one(
                        {"_id": invoice["_id"]},
                        {"$set": {"claimed_paid": True, "claim_received_at": now}},
                    )

                # Auto-reply to debtor (use platform default Unipile — no per-client doc here)
                auto_reply = result.get("auto_reply", "")
                if auto_reply:
                    try:
                        await send_whatsapp_for_client(phone=sender_phone, message=auto_reply)
                        log_doc["auto_reply_sent"] = True
                    except Exception as e:
                        log.warning("auto_reply_failed", error=str(e))

                # Notify the client who sent the invoice
                bursar_summary = result.get("notify_bursar", "")
                client_name = invoice.get("client_name", "")
                if bursar_summary and client_name:
                    # Look up client's phone from clients collection
                    client_doc = _db()["clients"].find_one(
                        {"name": {"$regex": f"^{client_name}$", "$options": "i"}},
                    )
                    client_phone = (client_doc or {}).get("whatsapp") or (client_doc or {}).get("contact_phone")
                    if client_phone and client_doc:
                        try:
                            await send_whatsapp_for_client(
                                phone=client_phone,
                                message=f"[ReachNG] {bursar_summary}",
                                client_doc=client_doc,
                            )
                            log_doc["bursar_notified"] = True
                        except Exception as e:
                            log.warning("client_notify_failed", error=str(e))

            except Exception as e:
                log.error("invoice_chaser_reply_processing_failed", error=str(e), phone=sender_phone)
                log_doc["processing_error"] = str(e)

    # ── Always log ────────────────────────────────────────────────────────────
    try:
        _db()["inbound_messages"].insert_one(log_doc)
    except Exception as e:
        log.error("inbound_log_failed", error=str(e))


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
