"""
Base campaign runner — shared logic for all verticals.
Each vertical subclass just defines its vertical name and preferred channel.
"""
import asyncio
import re
from typing import Optional
from tools import (
    discover_businesses, discover_apify_leads, upsert_contact, has_been_contacted,
    is_daily_limit_reached, record_outreach, get_daily_send_count,
    send_whatsapp, send_email,
)
from tools.outreach import send_whatsapp_for_client
from tools.hitl import queue_draft, get_pending, approve_draft, edit_draft
from tools.roi import log_roi_event
from tools.notifier import notify_whatsapp as notify_owner_whatsapp
from tools.social import discover_social_leads
from tools.ab_testing import assign_variant, record_ab_send
from tools.enrichment import enrich_business, format_enrichment_for_prompt
from agent import generate_outreach_message, generate_outreach_message_for_client, should_contact, generate_social_outreach_message
from config import get_settings
import structlog

log = structlog.get_logger()


class BaseCampaign:
    vertical: str = ""                  # Override in subclass
    preferred_channel: str = "whatsapp" # Override in subclass
    multi_channel: bool = False          # If True, queue drafts for ALL available channels

    async def run(
        self,
        max_new_contacts: int = 60,
        dry_run: bool = False,
        hitl_mode: bool = False,
        query_override: Optional[str] = None,
        client_name: Optional[str] = None,
        cities: Optional[list] = None,
        target_sectors: Optional[list] = None,
        min_rating: Optional[float] = None,
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
        log.info("campaign_start", vertical=self.vertical, dry_run=dry_run, hitl_mode=hitl_mode, client=client_name)

        # Agency mode: pull client config to personalise messages + route via their accounts
        client_brief = None
        client_whatsapp_account_id = None
        client_email_account_id = None
        client_city = None
        _client_doc = None
        if client_name:
            from api.clients import get_clients
            _client_doc = get_clients().find_one(
                {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}, "active": True}
            )
            if _client_doc:
                client_brief = _client_doc.get("brief")
                client_whatsapp_account_id = _client_doc.get("whatsapp_account_id")
                client_email_account_id    = _client_doc.get("email_account_id")
                client_city                = _client_doc.get("city")
                # Multi-city from client config (overrides cities param if set)
                if not cities and _client_doc.get("cities"):
                    cities = _client_doc["cities"]
                if _client_doc.get("preferred_channel"):
                    self.preferred_channel = _client_doc["preferred_channel"]
                log.info("campaign_client_config",
                         client=client_name,
                         provider=_client_doc.get("whatsapp_provider", "unipile"),
                         cities=cities or client_city)

        sent = 0
        queued = 0
        skipped_contacted = 0
        skipped_no_channel = 0
        errors = 0

        # Step 1: Discover — Google Maps + Apollo + Social + Signal Intelligence (run in parallel)
        # Fetch 2x max_new_contacts per source so filters have candidates to work with,
        # but keep a sensible floor of 5 to avoid empty discovery on small runs.
        from tools.signal_intelligence import discover_signal_leads
        fetch_quota   = max(5, max_new_contacts * 2)
        maps_quota    = max(5, fetch_quota // 4)
        apify_quota   = max(5, fetch_quota // 4)
        social_quota  = max(5, fetch_quota // 4)
        signal_quota  = fetch_quota - maps_quota - apify_quota - social_quota

        # Multi-city: run Maps + Apollo per city in parallel, then flatten
        target_cities = cities if cities else ([client_city] if client_city else [None])
        per_city_quota = max(3, maps_quota // len(target_cities))
        per_city_apify  = max(3, apify_quota // len(target_cities))

        is_client_campaign = bool(client_name)
        city_tasks = []
        for city in target_cities:
            city_tasks.append(discover_businesses(
                vertical=self.vertical, max_results=per_city_quota,
                query_override=query_override, city_override=city,
                target_sectors=target_sectors,
                is_client_campaign=is_client_campaign,
            ))
            city_tasks.append(discover_apify_leads(
                vertical=self.vertical, max_results=per_city_apify, city_override=city,
            ))
        city_tasks.append(discover_social_leads(vertical=self.vertical, max_results=social_quota))
        city_tasks.append(discover_signal_leads(vertical=self.vertical, max_results=signal_quota))

        all_results = await asyncio.gather(*city_tasks, return_exceptions=True)

        maps_leads, apify_leads, social_leads, signal_leads = [], [], [], []
        # Results interleaved: [maps_city1, apify_city1, maps_city2, apify_city2, ..., social, signal]
        for i, city in enumerate(target_cities):
            r_maps  = all_results[i * 2]
            r_apify = all_results[i * 2 + 1]
            if isinstance(r_maps, Exception):
                log.error("maps_discovery_failed", city=city, error=str(r_maps))
            else:
                maps_leads.extend(r_maps)
            if isinstance(r_apify, Exception):
                log.error("apify_discovery_failed", city=city, error=str(r_apify))
            else:
                apify_leads.extend(r_apify)
        r_social = all_results[-2]
        r_signal = all_results[-1]
        if isinstance(r_social, Exception):
            log.error("social_discovery_failed", error=str(r_social))
        else:
            social_leads = r_social
        if isinstance(r_signal, Exception):
            log.error("signal_discovery_failed", error=str(r_signal))
        else:
            signal_leads = r_signal

        if cities:
            log.info("multi_city_discovery", cities=cities, maps=len(maps_leads), apify=len(apify_leads))

        # ── Auto-expand to nearby cities if local pool is thin ─────────────────
        # Threshold: if we found fewer than CITY_EXPAND_THRESHOLD * max_new_contacts
        # unique leads, the local pool is running low — expand to nearby cities.
        total_found = len(maps_leads) + len(apify_leads) + len(social_leads)
        expand_threshold = max(3, int(max_new_contacts * settings.city_expand_threshold))
        primary_city = (client_city or settings.default_city).split(",")[0].strip()

        if total_found < expand_threshold and not cities:
            from tools.discovery import get_expansion_cities
            expansion_cities = get_expansion_cities(primary_city, max_expansions=2)
            if expansion_cities:
                log.info("city_pool_thin_expanding",
                         primary_city=primary_city,
                         found=total_found,
                         threshold=expand_threshold,
                         expanding_to=expansion_cities)
                expand_tasks = []
                for ecity in expansion_cities:
                    expand_tasks.append(discover_businesses(
                        vertical=self.vertical, max_results=per_city_quota,
                        query_override=query_override, city_override=ecity,
                        target_sectors=target_sectors,
                        is_client_campaign=is_client_campaign,
                    ))
                    expand_tasks.append(discover_apify_leads(
                        vertical=self.vertical, max_results=per_city_apify, city_override=ecity,
                    ))
                expand_results = await asyncio.gather(*expand_tasks, return_exceptions=True)
                for i, ecity in enumerate(expansion_cities):
                    r_m = expand_results[i * 2]
                    r_a = expand_results[i * 2 + 1]
                    if not isinstance(r_m, Exception):
                        maps_leads.extend(r_m)
                    if not isinstance(r_a, Exception):
                        apify_leads.extend(r_a)
                log.info("city_expansion_done",
                         maps_total=len(maps_leads), apify_total=len(apify_leads))

        # Deduplicate across sources by phone + email
        seen_phones: set[str] = set()
        seen_emails: set[str] = set()
        def _is_duplicate(b: dict) -> bool:
            phone = b.get("phone")
            email = b.get("email")
            if phone and phone in seen_phones:
                return True
            if email and email in seen_emails:
                return True
            if phone:
                seen_phones.add(phone)
            if email:
                seen_emails.add(email)
            return False

        # Sort: temperature DESC (hot first), then lead_score DESC within same temp
        # Signal leads come first as they carry the strongest purchase intent
        from tools.scoring import score_contact
        def _sort_key(b: dict) -> tuple:
            temp = b.get("lead_temperature", 0)
            score = score_contact(
                vertical=self.vertical,
                rating=b.get("rating"),
                has_phone=bool(b.get("phone")),
                has_website=bool(b.get("website")),
                category=b.get("category"),
            )
            return (temp, score)

        all_leads = signal_leads + social_leads + apify_leads + maps_leads
        all_leads.sort(key=_sort_key, reverse=True)
        businesses = [b for b in all_leads if not _is_duplicate(b)]

        hot_count  = sum(1 for b in businesses if b.get("lead_temperature", 0) == 2)
        warm_count = sum(1 for b in businesses if b.get("lead_temperature", 0) == 1)
        log.info("discovery_done", vertical=self.vertical, maps=len(maps_leads),
                 apify=len(apify_leads), social=len(social_leads), signal=len(signal_leads),
                 total_deduped=len(businesses), hot=hot_count, warm=warm_count)

        for biz in businesses:
            # Hard cap — stop once we've sent/queued/dry-run'd enough
            if (sent + queued) >= max_new_contacts:
                break

            # Step 2: Daily limit check (per-client override if set, else global)
            client_limit = _client_doc.get("daily_send_limit") if _client_doc else None
            if is_daily_limit_reached(client_limit=client_limit):
                log.info("daily_limit_reached", sent=sent, limit=client_limit or "global")
                break

            # Step 3: Skip if already contacted — scoped to client in agency mode
            if has_been_contacted(biz["place_id"], client_name=client_name):
                skipped_contacted += 1
                continue

            # Step 3.5: Rating filter — skip if below minimum threshold
            if min_rating is not None:
                biz_rating = biz.get("rating")
                if biz_rating is None or biz_rating < min_rating:
                    skipped_no_channel += 1
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

            # Step 5.5: Deep personalization — crawl website before writing
            enrichment_ctx = ""
            if biz.get("website") and not biz.get("source") == "social":
                enrichment = await enrich_business(website=biz["website"], business_name=biz["name"])
                enrichment_ctx = format_enrichment_for_prompt(enrichment, biz["name"])
                # Backfill email from website crawl if Maps didn't return one
                if enrichment.get("email") and not biz.get("email"):
                    biz["email"] = enrichment["email"]
                    # Re-evaluate channel now that email is available
                    channel = self._pick_channel(biz) or channel

            # Step 6: Generate message — social leads get post-aware opener
            try:
                if biz.get("source") == "social" and biz.get("post_text"):
                    generated = generate_social_outreach_message(
                        vertical=self.vertical,
                        business_name=biz["name"],
                        channel=channel,
                        platform=biz.get("platform", "social"),
                        post_text=biz["post_text"],
                        profile_url=biz.get("profile_url", ""),
                        address=biz.get("address"),
                    )
                elif client_brief:
                    generated = generate_outreach_message_for_client(
                        vertical=self.vertical,
                        business_name=biz["name"],
                        channel=channel,
                        client_context=client_brief,
                        address=biz.get("address"),
                        category=biz.get("category"),
                        rating=biz.get("rating"),
                        website=biz.get("website"),
                        is_followup=False,
                    )
                else:
                    generated = generate_outreach_message(
                        vertical=self.vertical,
                        business_name=biz["name"],
                        channel=channel,
                        address=biz.get("address"),
                        category=biz.get("category"),
                        rating=biz.get("rating"),
                        website=biz.get("website"),
                        is_followup=False,
                        enrichment_context=enrichment_ctx,
                        contact_name=biz.get("contact_name"),
                        contact_title=biz.get("contact_title"),
                    )
            except Exception as e:
                log.error("message_generation_failed", business=biz["name"], error=str(e))
                errors += 1
                continue

            if dry_run:
                log.info("dry_run_message", business=biz["name"], channel=channel, message=generated)
                sent += 1
                continue

            # Upsert contact record (only on real runs, not dry runs)
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
                client_name=client_name,
                source=biz.get("source", "maps"),
                platform=biz.get("platform"),
                lead_temperature=biz.get("lead_temperature", 0),
                temperature_reason=biz.get("temperature_reason"),
            )

            # Step 7a: HITL mode — queue for human approval instead of sending
            if hitl_mode:
                # Determine which channels to queue
                channels_to_queue = [channel]
                if self.multi_channel:
                    if channel == "whatsapp" and biz.get("email"):
                        channels_to_queue.append("email")
                    elif channel == "email" and biz.get("phone"):
                        channels_to_queue.insert(0, "whatsapp")

                for ch in channels_to_queue:
                    queue_draft(
                        contact_id=contact_id,
                        contact_name=biz["name"],
                        vertical=self.vertical,
                        channel=ch,
                        message=generated.get("message", ""),
                        subject=generated.get("subject"),
                        phone=biz.get("phone"),
                        email=biz.get("email"),
                        source=biz.get("source", "maps"),
                        platform=biz.get("platform"),
                        post_context=biz.get("post_text"),
                        profile_url=biz.get("profile_url"),
                    )
                    queued += 1
                continue

            # Step 7b: Send directly — routed via client's provider (Meta or Unipile)
            try:
                result = await self._send(
                    channel, biz, generated,
                    whatsapp_account_id=client_whatsapp_account_id,
                    email_account_id=client_email_account_id,
                    client_doc=_client_doc,
                )
                if not result.get("success", True):
                    log.warning("send_failed", business=biz["name"], result=result)
                    errors += 1
                    continue
            except Exception as e:
                log.error("send_error", business=biz["name"], error=str(e))
                errors += 1
                continue

            # Step 8: Record + ROI + A/B
            message_text = generated.get("message", str(generated))
            variant = assign_variant()
            record_outreach(
                contact_id=contact_id,
                channel=channel,
                message=message_text,
                attempt_number=1,
            )
            record_ab_send(
                contact_id=contact_id,
                vertical=self.vertical,
                channel=channel,
                variant=variant,
                message=message_text,
            )
            log_roi_event(
                contact_name=biz["name"],
                vertical=self.vertical,
                channel=channel,
                client_name=client_name,
            )
            sent += 1

            # Human-mimicry delay — randomised interval mimics a human typing/sending.
            # Fixed intervals get WhatsApp accounts flagged by anti-spam AI.
            # Range: 45–210 seconds, weighted toward 60–120s (natural typing pace).
            import random
            jitter = random.choices(
                [random.uniform(45, 75), random.uniform(75, 150), random.uniform(150, 210)],
                weights=[0.5, 0.35, 0.15],
            )[0]
            log.debug("human_jitter", seconds=round(jitter, 1), next_contact="pending")
            await asyncio.sleep(jitter)

        # Notify owner if drafts are queued for approval
        if hitl_mode and queued > 0:
            settings = get_settings()
            if settings.owner_whatsapp:
                await notify_owner_whatsapp(
                    contact_name="ReachNG",
                    vertical=self.vertical,
                    channel="system",
                    reply_text="",
                    intent="system",
                    urgency="medium",
                    summary=f"{queued} outreach draft(s) are ready for your approval on the dashboard.",
                )

        summary = {
            "vertical": self.vertical,
            "sent": sent,
            "queued_for_approval": queued,
            "skipped_already_contacted": skipped_contacted,
            "skipped_no_channel": skipped_no_channel,
            "errors": errors,
            "daily_total_sent": get_daily_send_count(),
            "dry_run": dry_run,
            "hitl_mode": hitl_mode,
            "discovery": {
                "maps":   len(maps_leads),
                "apify": len(apify_leads),
                "social": len(social_leads),
                "total_after_dedup": len(businesses),
            },
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
            if is_daily_limit_reached(client_limit=None):
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
            import random
            await asyncio.sleep(random.uniform(60, 180))

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

    async def _send(
        self,
        channel: str,
        biz: dict,
        generated: dict,
        whatsapp_account_id: Optional[str] = None,
        email_account_id: Optional[str] = None,
        client_doc: Optional[dict] = None,
    ) -> dict:
        if channel == "whatsapp":
            # Routes to Meta Cloud API or Unipile based on client config
            return await send_whatsapp_for_client(
                phone=biz["phone"],
                message=generated["message"],
                client_doc=client_doc,
            )
        elif channel == "email":
            return await send_email(
                to_email=biz["email"],
                subject=generated.get("subject", f"Quick question for {biz['name']}"),
                body=generated["message"],
                account_id=email_account_id,
            )
        raise ValueError(f"Unknown channel: {channel}")
