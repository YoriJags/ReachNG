"""
Base campaign runner — shared logic for all verticals.
Each vertical subclass just defines its vertical name and preferred channel.
"""
import asyncio
from typing import Optional
from tools import (
    discover_businesses, upsert_contact, has_been_contacted,
    is_daily_limit_reached, record_outreach, get_daily_send_count,
    send_whatsapp, send_email,
)
from agent import generate_outreach_message, should_contact
from config import get_settings
import structlog

log = structlog.get_logger()


class BaseCampaign:
    vertical: str = ""                  # Override in subclass
    preferred_channel: str = "whatsapp" # Override in subclass

    async def run(
        self,
        max_new_contacts: int = 60,
        dry_run: bool = False,
        query_override: Optional[str] = None,
    ) -> dict:
        """
        Full campaign run:
        1. Discover businesses
        2. Filter already-contacted
        3. Generate personalised message per contact
        4. Send via preferred channel
        5. Record in MongoDB
        Returns summary stats.
        """
        settings = get_settings()
        log.info("campaign_start", vertical=self.vertical, dry_run=dry_run)

        sent = 0
        skipped_contacted = 0
        skipped_no_channel = 0
        errors = 0

        # Step 1: Discover
        businesses = await discover_businesses(
            vertical=self.vertical,
            max_results=max_new_contacts,
            query_override=query_override,
        )
        log.info("discovery_done", vertical=self.vertical, found=len(businesses))

        for biz in businesses:
            # Step 2: Daily limit check
            if is_daily_limit_reached():
                log.info("daily_limit_reached", sent=sent)
                break

            # Upsert contact record
            contact_id = upsert_contact(
                place_id=biz["place_id"],
                name=biz["name"],
                vertical=self.vertical,
                phone=biz.get("phone"),
                email=biz.get("email"),
                address=biz.get("address"),
                website=biz.get("website"),
                rating=biz.get("rating"),
                category=biz.get("category"),
            )

            # Step 3: Skip if already contacted
            if has_been_contacted(biz["place_id"]):
                skipped_contacted += 1
                continue

            # Step 4: Quality filter
            if not should_contact(
                business_name=biz["name"],
                vertical=self.vertical,
                rating=biz.get("rating"),
                has_phone=bool(biz.get("phone")),
                has_website=bool(biz.get("website")),
            ):
                skipped_no_channel += 1
                continue

            # Step 5: Determine channel
            channel = self._pick_channel(biz)
            if not channel:
                skipped_no_channel += 1
                continue

            # Step 6: Generate message
            try:
                generated = generate_outreach_message(
                    vertical=self.vertical,
                    business_name=biz["name"],
                    channel=channel,
                    address=biz.get("address"),
                    category=biz.get("category"),
                    rating=biz.get("rating"),
                    website=biz.get("website"),
                    is_followup=False,
                )
            except Exception as e:
                log.error("message_generation_failed", business=biz["name"], error=str(e))
                errors += 1
                continue

            if dry_run:
                log.info(
                    "dry_run_message",
                    business=biz["name"],
                    channel=channel,
                    message=generated,
                )
                sent += 1
                continue

            # Step 7: Send
            try:
                result = await self._send(channel, biz, generated)
                if not result.get("success", True):
                    log.warning("send_failed", business=biz["name"], result=result)
                    errors += 1
                    continue
            except Exception as e:
                log.error("send_error", business=biz["name"], error=str(e))
                errors += 1
                continue

            # Step 8: Record
            message_text = generated.get("message", str(generated))
            record_outreach(
                contact_id=contact_id,
                channel=channel,
                message=message_text,
                attempt_number=1,
            )
            sent += 1

            # Polite delay — don't hammer APIs
            await asyncio.sleep(1.5)

        summary = {
            "vertical": self.vertical,
            "sent": sent,
            "skipped_already_contacted": skipped_contacted,
            "skipped_no_channel": skipped_no_channel,
            "errors": errors,
            "daily_total_sent": get_daily_send_count(),
            "dry_run": dry_run,
        }
        log.info("campaign_complete", **summary)
        return summary

    async def run_followups(self, dry_run: bool = False) -> dict:
        """Send follow-up messages to contacts due for a second touch."""
        from tools import get_followup_candidates

        candidates = get_followup_candidates(vertical=self.vertical)
        sent = 0
        errors = 0

        for contact in candidates:
            if is_daily_limit_reached():
                break

            attempt = contact.get("outreach_count", 1) + 1
            channel = contact.get("preferred_channel") or self.preferred_channel

            # Need phone for WhatsApp, skip if missing
            if channel == "whatsapp" and not contact.get("phone"):
                continue

            try:
                generated = generate_outreach_message(
                    vertical=self.vertical,
                    business_name=contact["name"],
                    channel=channel,
                    address=contact.get("address"),
                    category=contact.get("category"),
                    rating=contact.get("rating"),
                    website=contact.get("website"),
                    is_followup=True,
                    attempt_number=attempt,
                )
            except Exception as e:
                log.error("followup_generation_failed", contact=contact["name"], error=str(e))
                errors += 1
                continue

            if not dry_run:
                try:
                    await self._send(channel, contact, generated)
                except Exception as e:
                    log.error("followup_send_failed", contact=contact["name"], error=str(e))
                    errors += 1
                    continue

                message_text = generated.get("message", str(generated))
                record_outreach(
                    contact_id=str(contact["_id"]),
                    channel=channel,
                    message=message_text,
                    attempt_number=attempt,
                )
            sent += 1
            await asyncio.sleep(1.5)

        return {"vertical": self.vertical, "followups_sent": sent, "errors": errors}

    def _pick_channel(self, biz: dict) -> Optional[str]:
        """Return best available channel for this contact."""
        if self.preferred_channel == "whatsapp" and biz.get("phone"):
            return "whatsapp"
        if biz.get("email"):
            return "email"
        if biz.get("phone"):
            return "whatsapp"
        return None

    async def _send(self, channel: str, biz: dict, generated: dict) -> dict:
        if channel == "whatsapp":
            return await send_whatsapp(
                phone=biz["phone"],
                message=generated["message"],
            )
        elif channel == "email":
            return await send_email(
                to_email=biz["email"],
                subject=generated.get("subject", f"Quick question for {biz['name']}"),
                body=generated["message"],
            )
        raise ValueError(f"Unknown channel: {channel}")
