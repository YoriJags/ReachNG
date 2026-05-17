"""
WhatsApp Inbound Webhook — handles replies from both Unipile and Meta Cloud API.

Flow for every inbound message:
1. Parse sender + body from Unipile or Meta payload
2. Link to a student (school fees) or invoice (invoice chaser) by phone number
3. Claude classifies the reply + generates a context-aware auto-reply
4. Auto-reply sent back to debtor on WhatsApp
5. Bursar/client forwarded a one-line notification on their WhatsApp
6. Everything logged to inbound_messages collection
"""
from fastapi import APIRouter, Request, Response
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


def _parse_meta(payload: dict) -> list[tuple[str, str, dict]]:
    """
    Returns (sender, body, raw_msg) per message. raw_msg lets the image branch
    look up `msg.type == "image"` and `msg.image.id` for media download.
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
                        results.append((sender, body, msg))
    except Exception as e:
        log.warning("meta_payload_parse_error", error=str(e))
    return results


# ─── Receipt Catcher pipeline (images on inbound) ─────────────────────────────

async def _handle_image_attachment(
    sender_phone: str,
    image_bytes: bytes,
    mime_type: str,
    source: str | None,
    client_id: str | None = None,    # T0.2.5 metering scope
) -> bool:
    """
    Try the Receipt Catcher pipeline on an inbound image.

    Returns True if we processed the image (matched + queued), False if we should
    fall through to text-only handling (e.g. vision call failed and there's a caption).
    """
    try:
        from tools.receipt_vision import extract_receipt
        from services.receipt_match import match_receipt, queue_receipt_ack
    except Exception as e:
        log.error("receipt_module_import_failed", error=str(e))
        return False

    try:
        # T0.2.5 — extract_receipt now records its own usage event + rate-limits internally
        receipt = await extract_receipt(image_bytes, mime_type, client_id=client_id)
    except Exception as e:
        log.error("receipt_vision_crashed", error=str(e), phone=sender_phone)
        return False

    if not receipt.is_receipt and receipt.confidence < 0.3:
        log.info("inbound_image_not_a_receipt", phone=sender_phone,
                 conf=receipt.confidence)
        return False  # let text branch handle the caption if any

    try:
        match = match_receipt(receipt, sender_phone)
        queue_receipt_ack(receipt, match, sender_phone)
        return True
    except Exception as e:
        log.error("receipt_match_or_queue_failed", error=str(e), phone=sender_phone)
        return False


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
    Always returns 200 — never retry-loops from either provider.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    is_meta = payload.get("object") == "whatsapp_business_account"

    # ── Early client lookup (T0.2.5 metering) ────────────────────────────────
    # Resolve the matched client BEFORE voice/receipt pipelines so we can
    # meter their cost against the right tenant. Best-effort: if we can't
    # match (e.g. Meta inbound where account_id is opaque), metering happens
    # with client_id=None and the call still proceeds.
    _early_client_id: str | None = None
    try:
        if not is_meta:
            _account_id = (payload.get("data", {}) or {}).get("account_id") or payload.get("account_id")
            if _account_id:
                _early = _db()["clients"].find_one(
                    {"whatsapp_account_id": _account_id, "active": True}, {"_id": 1})
                if _early:
                    _early_client_id = str(_early["_id"])
    except Exception:
        pass

    # ── Voice-note transcription (T0.1) — runs FIRST so transcript becomes text ──
    # If the inbound carries a voice note / audio attachment, transcribe it via
    # Whisper and substitute the transcript as the message body so every
    # downstream handler (Closer intake, rent matcher, invoice matcher, drafter)
    # treats it identically to a typed message. Keyed by sender_phone.
    voice_transcripts: dict[str, str] = {}  # sender_phone → transcript text
    try:
        if is_meta:
            from tools.inbound_media import extract_meta_audio, download_meta_media
            from tools.voice_whisper import transcribe_voice_note, format_for_draft
            for sender, _body, raw_msg in _parse_meta(payload):
                aud = extract_meta_audio(raw_msg)
                if not aud:
                    continue
                media_id, mime = aud
                try:
                    audio_bytes, fetched_mime = await download_meta_media(media_id)
                    # T0.2.5 — transcribe_voice_note now records its own usage event + rate-limits internally
                    tr = await transcribe_voice_note(audio_bytes, fetched_mime or mime,
                                                      client_id=_early_client_id)
                    if tr and tr.text:
                        voice_transcripts[sender] = format_for_draft(tr)
                        log.info("voice_note_transcribed", sender=sender,
                                 dur=tr.duration_seconds, chars=len(tr.text))
                except Exception as e:
                    log.error("meta_audio_pipeline_failed", error=str(e), sender=sender)
        else:
            from tools.inbound_media import extract_unipile_audio, download_unipile_attachment
            from tools.voice_whisper import transcribe_voice_note, format_for_draft
            data = payload.get("data", {})
            sender_p = data.get("from") or payload.get("from")
            aud = extract_unipile_audio(data)
            if sender_p and aud:
                msg_id, att_id, mime = aud
                try:
                    audio_bytes, fetched_mime = await download_unipile_attachment(msg_id, att_id)
                    tr = await transcribe_voice_note(audio_bytes, fetched_mime or mime,
                                                      client_id=_early_client_id)
                    if tr and tr.text:
                        voice_transcripts[sender_p] = format_for_draft(tr)
                        log.info("voice_note_transcribed", sender=sender_p,
                                 dur=tr.duration_seconds, chars=len(tr.text))
                except Exception as e:
                    log.error("unipile_audio_pipeline_failed", error=str(e), sender=sender_p)
    except Exception as e:
        log.error("inbound_audio_dispatch_crashed", error=str(e))

    # ── Receipt Catcher: images get processed FIRST, separately from text ────
    # If the inbound message is an image (or has an image attachment), run the
    # Receipt Catcher pipeline. If it's a pure image (no caption), we short-circuit.
    # If it has a caption, we ALSO run the text handler so we don't drop context.
    image_handled_for: set[str] = set()
    try:
        if is_meta:
            from tools.inbound_media import extract_meta_image, download_meta_media
            for sender, _body, raw_msg in _parse_meta(payload):
                img = extract_meta_image(raw_msg)
                if not img:
                    continue
                media_id, mime = img
                try:
                    image_bytes, fetched_mime = await download_meta_media(media_id)
                    if await _handle_image_attachment(sender, image_bytes,
                                                      fetched_mime or mime, "meta",
                                                      client_id=_early_client_id):
                        image_handled_for.add(sender)
                except Exception as e:
                    log.error("meta_image_pipeline_failed", error=str(e), sender=sender)
        else:
            from tools.inbound_media import extract_unipile_image, download_unipile_attachment
            data = payload.get("data", {})
            sender_p = data.get("from") or payload.get("from")
            img = extract_unipile_image(data)
            if sender_p and img:
                msg_id, att_id, mime = img
                try:
                    image_bytes, fetched_mime = await download_unipile_attachment(msg_id, att_id)
                    if await _handle_image_attachment(sender_p, image_bytes,
                                                      fetched_mime or mime, "unipile",
                                                      client_id=_early_client_id):
                        image_handled_for.add(sender_p)
                except Exception as e:
                    log.error("unipile_image_pipeline_failed", error=str(e), sender=sender_p)
    except Exception as e:
        log.error("inbound_image_dispatch_crashed", error=str(e))

    # ── Text handler — also runs for pure images, with a synthetic body ─────
    # We never short-circuit the text handler. If the inbound was a pure image
    # (no caption), we substitute a synthetic body so the Closer thread / rent /
    # invoice intakes still capture the moment. Receipt acknowledgement is queued
    # in parallel by the image pipeline above — the customer feels one cohesive chat.
    # `skip_autodraft` suppresses the Closer auto-draft for pure-image inbounds so
    # we don't queue two competing drafts (receipt ack already covers it).
    messages_to_process: list[tuple[str | None, str, str | None, bool]] = []
    synthetic_body = "[Image received — receipt extraction in progress]"

    if is_meta:
        for sender, body, _raw in _parse_meta(payload):
            effective_body = body
            skip_ad = False
            # Voice transcript takes precedence over empty/null body. If the
            # customer included a caption AND a voice note, concatenate.
            if sender in voice_transcripts:
                v_text = voice_transcripts[sender]
                effective_body = f"{v_text}\n\n{body}".strip() if (body or "").strip() else v_text
            elif sender in image_handled_for and not (body or "").strip():
                effective_body = synthetic_body
                skip_ad = True
            messages_to_process.append((sender, effective_body, "meta", skip_ad))
    else:
        sender, body, account_id = _parse_unipile(payload)
        effective_body = body
        skip_ad = False
        if sender in voice_transcripts:
            v_text = voice_transcripts[sender]
            effective_body = f"{v_text}\n\n{body}".strip() if (body or "").strip() else v_text
        elif sender in image_handled_for and not (body or "").strip():
            effective_body = synthetic_body
            skip_ad = True
        messages_to_process.append((sender, effective_body, account_id, skip_ad))

    for sender_phone, message_body, source, skip_ad in messages_to_process:
        if not sender_phone:
            continue
        try:
            await _handle_message(
                sender_phone, message_body, source,
                payload.get("event", "message.received"),
                skip_autodraft=skip_ad,
            )
        except Exception as e:
            log.error("inbound_handler_crashed", error=str(e), phone=sender_phone)

    return {"ok": True}


async def _handle_message(
    sender_phone: str,
    message_body: str,
    source: str | None,
    event: str,
    skip_autodraft: bool = False,
):
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

    # ── Memory learning — fire-and-forget after matched_client resolves ─────
    # We extract durable facts from the inbound and store them scoped to
    # (client_id, sender_phone). Pure-image inbounds (synthetic body) are skipped.
    def _maybe_learn_memory(client_doc: dict | None, body_text: str) -> None:
        if not client_doc or not body_text or body_text.startswith("[Image received"):
            return
        try:
            from services.client_memory import learn_from_inbound
            learn_from_inbound(
                client_id=str(client_doc["_id"]),
                contact_phone=sender_phone,
                inbound_text=body_text,
                vertical=client_doc.get("vertical"),
            )
        except Exception as _e:
            log.warning("memory_learn_failed", error=str(_e))

    # ── Outcome learning — resolve open outcomes from this inbound (T0.4) ───
    # If the classifier reads this inbound as positive (booked/paid/yes) or
    # negative (no/complaint), tag any open outcomes against this contact.
    def _maybe_resolve_outcomes(client_doc: dict | None, body_text: str) -> None:
        if not client_doc or not body_text or body_text.startswith("[Image received"):
            return
        try:
            from services.inbound_classifier import classify_inbound
            from services.outcome_learning import tag_from_inbound
            cls = classify_inbound(body_text)
            intent = (cls.get("intent") if isinstance(cls, dict) else None) or \
                     (cls.get("stage") if isinstance(cls, dict) else None)
            if not intent:
                return
            tag_from_inbound(
                contact_phone=sender_phone,
                client_id=str(client_doc["_id"]),
                intent=intent,
                raw_text=body_text,
            )
        except Exception as _e:
            log.warning("outcome_resolve_failed", error=str(_e))

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
                # Learn durable facts from this inbound (scoped to client + contact)
                _maybe_learn_memory(matched_client, message_body)
                # Tag any open outcomes against this contact based on classifier
                _maybe_resolve_outcomes(matched_client, message_body)
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
                    # Skipped when Receipt Catcher already queued an acknowledgement.
                    if not skip_autodraft:
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
                    # Skipped when Receipt Catcher already queued an acknowledgement.
                    if not skip_autodraft:
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
