"""
Closer reply auto-drafting.

When an inbound reply arrives on a Closer lead, this module:
  1. Reads the lead's recent thread
  2. Asks Claude to classify what stage the conversation is at
  3. Picks the right drafter intent (qualifier / objection_handler / booking / followup)
  4. Generates the next message using the client's BusinessBrief context
  5. Queues the draft via HITL — never auto-sends
  6. Optionally bumps the lead's stage when the AI is confident

The owner sees the draft alongside the inbound message in the Message Queue
and approves, edits, or skips. No outbound goes without a human tap.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import anthropic
from bson import ObjectId

from config import get_settings
from services.brief import assemble_context
from services.closer.store import get_lead, update_stage, VALID_STAGES
from tools.hitl import queue_draft, BriefIncompleteError
from tools.account_guard import OutreachCapExceeded, OutreachPaused
import structlog

log = structlog.get_logger()


# Stage → drafter intent mapping. Drafter intents come from services.brief.context.
_STAGE_TO_INTENT = {
    "new":        "outreach_warm",
    "qualifying": "qualifier",
    "ready":      "booking",
    "booked":     "followup",
    "stalled":    "followup",
    "lost":       None,        # don't draft — lead is dead
}


_CLASSIFIER_SYSTEM = """You are reading the latest reply on a real-estate Closer thread.
Classify what to do next. Return STRICT JSON only — no prose, no code fences.

Schema:
{
  "next_intent": "qualifier" | "objection_handler" | "booking" | "followup" | "stop",
  "next_stage":  "qualifying" | "ready" | "booked" | "stalled" | "lost",
  "objection":   "<short string if next_intent=objection_handler else empty>",
  "confidence":  "high" | "medium" | "low",
  "reasoning":   "<one sentence — why you picked this>"
}

Rules:
- "stop" if the customer has clearly opted out, said never again, or asked to be removed.
- "objection_handler" only when there's a real objection in the latest message (price, fees, comparison, hesitation).
- "booking" only when the customer has said yes to next step or asked when/where to view.
- "qualifier" when budget/timeline/area still unknown and you need to ask.
- "followup" when the customer is non-committal but not opposed — maintain warmth.
"""


def draft_next_move(lead_id: str) -> Optional[dict]:
    """Generate and queue the next outbound draft for a Closer lead.

    Returns: {approval_id, intent, next_stage, confidence} or None if skipped.
    Skips silently and logs when:
      - the lead is missing / lost / booked
      - the brief gate raises (logged, lead untouched)
      - the AI says "stop"
    """
    lead = get_lead(lead_id)
    if not lead:
        return None

    current_stage = lead.get("stage")
    if current_stage in ("lost", "booked"):
        return None

    classification = _classify(lead)
    if not classification:
        return None
    if classification.get("next_intent") == "stop":
        # Treat as lost — won't be re-drafted on subsequent replies.
        try:
            update_stage(lead_id, "lost")
        except Exception:
            pass
        return None

    intent = classification.get("next_intent") or _STAGE_TO_INTENT.get(current_stage) or "followup"
    next_stage = classification.get("next_stage")
    objection = classification.get("objection") or ""

    client_name = lead.get("client_name")
    contact_name = lead.get("contact_name") or "the lead"

    ctx = assemble_context(
        client_name=client_name,
        intent=intent,
        extra_context={"objection": objection} if objection else None,
    )

    # ── Inject memory, KB chunks, and active rules ───────────────────────────
    system_prompt = ctx["system_prompt"]

    # ── Agent identity (T0.2.6) — sign-off name, customer perceives them
    #    as the business's in-house employee, never as "ReachNG".
    try:
        from agent.brain import _agent_identity_block, _payment_details_block
        identity = _agent_identity_block(client_name)
        if identity:
            system_prompt = identity + "\n\n" + system_prompt
        payment = _payment_details_block(client_name)
        if payment:
            system_prompt = payment + "\n\n" + system_prompt
    except Exception as _e:
        log.warning("identity_inject_closer_failed", error=str(_e))
    contact_phone = lead.get("contact_phone")
    lead_client_id = lead.get("client_id")
    last_inbound = (lead.get("inquiry_text") or "")
    # Find the freshest inbound from the thread if available
    for ev in reversed(lead.get("thread") or []):
        if ev.get("direction") == "in" and ev.get("body"):
            last_inbound = ev["body"]
            break

    if lead_client_id and contact_phone:
        try:
            from services.client_memory import fetch_memory_block
            mem = fetch_memory_block(
                client_id=str(lead_client_id),
                contact_phone=contact_phone,
                requested_by="closer.draft_next_move",
            )
            if mem:
                system_prompt = system_prompt + "\n\n" + mem
        except Exception as _e:
            log.warning("memory_inject_closer_failed", lead=lead_id, error=str(_e))

    if lead_client_id:
        try:
            from services.knowledge_base import fetch_kb_block
            kb = fetch_kb_block(str(lead_client_id), last_inbound)
            if kb:
                system_prompt = system_prompt + "\n\n" + kb
        except Exception as _e:
            log.warning("kb_inject_closer_failed", lead=lead_id, error=str(_e))

        try:
            from services.client_rules import fetch_rules_block
            rules_block, escalate_flag = fetch_rules_block(str(lead_client_id), last_inbound, intent=intent)
            if rules_block:
                system_prompt = system_prompt + "\n\n" + rules_block
            if escalate_flag:
                # Stash escalation flag on the lead so the operator UI can render it
                try:
                    from database import get_db as _gdb
                    from bson import ObjectId
                    _gdb()["closer_leads"].update_one(
                        {"_id": ObjectId(lead_id)},
                        {"$set": {"escalation_flag": True,
                                  "escalation_reason": "rule-triggered escalation"}},
                    )
                except Exception:
                    pass
        except Exception as _e:
            log.warning("rules_inject_closer_failed", lead=lead_id, error=str(_e))

    # ── Emotional read on the latest inbound (T0.2) ────────────────────────
    classification_dict: Optional[dict] = None
    try:
        from services.inbound_classifier import classify_inbound, format_tone_block
        if last_inbound and last_inbound.strip():
            # Build a small thread-context window for sharper classification
            recent_ctx = ""
            try:
                tail = (lead.get("thread") or [])[-4:]
                recent_ctx = "\n".join(
                    f"{(ev.get('direction') or '?')}: {(ev.get('body') or '')[:140]}"
                    for ev in tail if ev.get("body")
                )
            except Exception:
                recent_ctx = ""
            c = classify_inbound(
                last_inbound,
                vertical=lead.get("vertical"),
                recent_context=recent_ctx or None,
                contact_name=contact_name,
                client_id=str(lead_client_id) if lead_client_id else None,
            )
            classification_dict = c.to_dict()
            system_prompt = system_prompt + "\n\n" + format_tone_block(c)
            # Persist on the lead doc for HITL queue badges + auto-escalation.
            try:
                from database import get_db as _gdb
                from bson import ObjectId
                update = {"$set": {"last_classification": classification_dict,
                                    "last_classified_at": datetime.now(timezone.utc)}}
                if c.escalate:
                    update["$set"]["escalation_flag"] = True
                    update["$set"]["escalation_reason"] = (
                        f"emotion read: {c.sentiment}/{c.stage}/{c.urgency}"
                    )
                _gdb()["closer_leads"].update_one({"_id": ObjectId(lead_id)}, update)
            except Exception as _e:
                log.warning("classification_persist_failed", lead=lead_id, error=str(_e))
    except Exception as _e:
        log.warning("classifier_inject_closer_failed", lead=lead_id, error=str(_e))

    # T0.2.5 rate-limit gate — anti-runaway on the drafter
    try:
        from services.usage_meter import check_rate
        if lead_client_id and not check_rate(str(lead_client_id), "drafter"):
            log.warning("closer_drafter_rate_limited", lead=lead_id, client_id=str(lead_client_id))
            return None
    except Exception:
        pass

    # Render the actual draft using the assembled system prompt + lead thread.
    user_prompt = _render_user_prompt(lead, intent)
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        log.error("closer_drafter_failed", lead=lead_id, error=str(e))
        return None

    # T0.2.5 record drafter call cost
    try:
        from services.usage_meter import record
        record(str(lead_client_id) if lead_client_id else None, "drafter", units=1)
    except Exception:
        pass

    draft_text = (msg.content[0].text or "").strip()
    if not draft_text:
        return None

    # Queue through HITL — brief gate + caps still apply.
    # The HITL layer fires the sales alerter automatically when classification
    # is set; we pass `inbound_context=last_inbound` so the alert ping to the
    # owner can include "They said: …" in the body.
    try:
        approval_id = queue_draft(
            contact_id=lead_id,                            # closer lead id doubles as contact id
            contact_name=contact_name,
            vertical=lead.get("vertical") or "general",
            channel="whatsapp",
            message=draft_text,
            phone=lead.get("contact_phone"),
            source="closer",
            client_name=client_name,
            classification=classification_dict,
            inbound_context=last_inbound,
        )
    except BriefIncompleteError as e:
        log.warning("closer_draft_blocked_brief", lead=lead_id, blockers=e.blockers)
        return None
    except (OutreachPaused, OutreachCapExceeded) as e:
        log.info("closer_draft_blocked_caps", lead=lead_id, reason=str(e))
        return None
    except Exception as e:
        log.error("closer_queue_failed", lead=lead_id, error=str(e))
        return None

    # Bump stage if the AI was confident — soft auto-progress, owner can override.
    if next_stage in VALID_STAGES and classification.get("confidence") == "high" and next_stage != current_stage:
        try:
            update_stage(lead_id, next_stage)
        except Exception:
            pass

    log.info(
        "closer_draft_queued",
        lead=lead_id,
        client=client_name,
        intent=intent,
        confidence=classification.get("confidence"),
        next_stage=next_stage,
    )
    return {
        "approval_id": approval_id,
        "intent": intent,
        "next_stage": next_stage,
        "confidence": classification.get("confidence"),
    }


# ─── Internal ────────────────────────────────────────────────────────────────

def _classify(lead: dict) -> Optional[dict]:
    """Ask Claude Haiku to classify the latest reply + recommend next intent.
    Falls back to None on any failure — caller treats as 'no draft'."""
    thread = lead.get("thread") or []
    if not thread:
        return None
    last = thread[-1]
    if last.get("direction") != "in":
        # Most recent message wasn't from the lead; nothing new to react to.
        return None

    convo_lines = []
    for msg in thread[-10:]:
        who = "LEAD" if msg.get("direction") == "in" else "US"
        body = (msg.get("body") or "").strip()
        if body:
            convo_lines.append(f"{who}: {body}")

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=_CLASSIFIER_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Current stage: {lead.get('stage')}\n"
                    f"Inquiry text (initial): {lead.get('inquiry_text') or ''}\n\n"
                    "Recent thread (oldest first):\n" + "\n".join(convo_lines)
                ),
            }],
        )
    except Exception as e:
        log.error("closer_classify_failed", lead=str(lead.get("id")), error=str(e))
        return None

    raw = (resp.content[0].text or "").strip()
    if raw.startswith("```"):
        # tolerate stray fences
        raw = raw.lstrip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.split("```")[0].strip()

    try:
        return json.loads(raw)
    except Exception:
        log.warning("closer_classify_parse_failed", preview=raw[:160])
        return None


def _render_user_prompt(lead: dict, intent: str) -> str:
    thread = lead.get("thread") or []
    recent = thread[-8:]
    convo = []
    for m in recent:
        who = "Lead" if m.get("direction") == "in" else "Us"
        body = (m.get("body") or "").strip()
        if body:
            convo.append(f"{who}: {body}")

    return (
        f"Drafting the next outbound WhatsApp message in this Closer thread.\n"
        f"Lead: {lead.get('contact_name') or 'unnamed'}\n"
        f"Initial inquiry: {lead.get('inquiry_text') or '(none captured)'}\n\n"
        f"Recent conversation:\n" + ("\n".join(convo) or "(no prior messages)") + "\n\n"
        f"Intent for this draft: {intent}.\n"
        f"Keep it under 60 words, WhatsApp-shaped. Match the system-prompt voice + closing action.\n"
        f"Return ONLY the message text. No prefix, no quotes, no explanation."
    )
