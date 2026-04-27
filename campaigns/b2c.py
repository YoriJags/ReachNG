"""
B2C Campaign Runner — sends personalized messages to a client's uploaded customer list.

Unlike B2B campaigns (which discover new leads), B2C campaigns work from contacts
already imported via CSV upload. No discovery step needed.

Flow:
  1. Pull B2C contacts for this client (not yet contacted / 14-day cooldown)
  2. For each contact: generate personalized message using name + notes + tags
  3. Send via WhatsApp (primary) or email fallback
  4. Record outreach + update contact status
  5. Queue for HITL approval if hitl_mode=True
"""
import asyncio
from typing import Optional
from tools.csv_import import get_b2c_contacts_for_campaign, mark_b2c_contacted
from tools.outreach import send_whatsapp, send_email
from tools.hitl import queue_draft
from tools.roi import log_roi_event
from tools.notifier import notify_whatsapp as notify_owner_whatsapp
from agent.brain import generate_b2c_message
from config import get_settings
import structlog

log = structlog.get_logger()


class B2CCampaign:
    """
    Campaign runner for B2C contacts imported via CSV.
    One instance per (client, vertical) pair.
    """

    async def run(
        self,
        client_name: str,
        vertical: str,
        max_contacts: int = 50,
        dry_run: bool = True,
        hitl_mode: bool = False,
        client_brief: Optional[str] = None,
        whatsapp_account_id: Optional[str] = None,
        email_account_id: Optional[str] = None,
    ) -> dict:
        settings = get_settings()
        log.info("b2c_campaign_start", client=client_name, vertical=vertical, dry_run=dry_run, max=max_contacts)

        contacts = get_b2c_contacts_for_campaign(
            client_name=client_name,
            vertical=vertical,
            limit=max_contacts,
        )

        sent = 0
        queued = 0
        skipped = 0
        errors = 0

        for contact in contacts:
            contact_id = str(contact["_id"])
            name   = contact.get("name", "Customer")
            phone  = contact.get("phone")
            email  = contact.get("email")
            notes  = contact.get("notes")
            tags   = contact.get("tags", [])

            # Pick channel
            channel = "whatsapp" if phone else ("email" if email else None)
            if not channel:
                skipped += 1
                continue

            # Generate message — passing client_name pulls the structured BusinessBrief.
            try:
                generated = generate_b2c_message(
                    customer_name=name,
                    channel=channel,
                    vertical=vertical,
                    client_brief=client_brief,
                    client_name=client_name,
                    notes=notes,
                    tags=tags,
                )
            except Exception as exc:
                log.error("b2c_message_generation_failed", contact=name, error=str(exc))
                errors += 1
                continue

            if dry_run:
                log.info("b2c_dry_run", contact=name, channel=channel, message=generated)
                sent += 1
                continue

            # HITL mode — queue for approval. source="byo_leads" so the brief
            # gate inside queue_draft hard-blocks if the brief regressed mid-run.
            if hitl_mode:
                queue_draft(
                    contact_id=contact_id,
                    contact_name=name,
                    vertical=vertical,
                    channel=channel,
                    message=generated.get("message", ""),
                    subject=generated.get("subject"),
                    phone=phone,
                    email=email,
                    source="byo_leads",
                    client_name=client_name,
                )
                queued += 1
                continue

            # Send directly
            success = False
            try:
                if channel == "whatsapp" and phone:
                    result = await asyncio.to_thread(
                        send_whatsapp,
                        phone=phone,
                        message=generated.get("message", ""),
                        account_id=whatsapp_account_id,
                    )
                    success = result.get("success", False)
                elif channel == "email" and email:
                    result = await asyncio.to_thread(
                        send_email,
                        to_email=email,
                        subject=generated.get("subject", "Hi from us"),
                        body=generated.get("message", ""),
                        account_id=email_account_id,
                    )
                    success = result.get("success", False)
            except Exception as exc:
                log.error("b2c_send_failed", contact=name, error=str(exc))
                errors += 1
                continue

            if success:
                mark_b2c_contacted(contact_id)
                log_roi_event(
                    vertical=vertical,
                    event_type="b2c_outreach_sent",
                    client_name=client_name,
                    channel=channel,
                )
                sent += 1
                log.info("b2c_sent", contact=name, channel=channel)

                # Notify owner on first send of each batch
                if sent == 1 and settings.owner_whatsapp:
                    await asyncio.to_thread(
                        notify_owner_whatsapp,
                        f"B2C campaign started: {client_name} / {vertical}. First message sent to {name}.",
                    )
            else:
                errors += 1

        summary = {
            "vertical": vertical,
            "client": client_name,
            "mode": "b2c",
            "dry_run": dry_run,
            "sent": sent,
            "queued_for_approval": queued,
            "skipped": skipped,
            "errors": errors,
            "total_contacts": len(contacts),
        }
        log.info("b2c_campaign_done", **summary)
        return summary
