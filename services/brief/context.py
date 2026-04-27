"""
assemble_context — the merger that AI drafters call.

Reads vertical primer + client business_brief (+ legacy closer_brief), produces
a single bundle the drafter can pass to Claude:

    {
      "system_prompt": "...",        # ready-to-send system prompt
      "tone": "warm-professional",
      "vocabulary": [...],
      "guardrails": {
          "never_say": [...],
          "compliance_notes": [...],
      },
      "qualifying_questions": [...],
      "closing_action": "...",
      "signature": "...",
      "client_name": "...",
      "vertical": "...",
    }

If a brief is missing or empty, the primer fills the gap. If both are missing
(vertical not seeded), returns a minimal safe context.
"""
from __future__ import annotations

from typing import Optional
from services.brief.store import get_brief, get_primer


# Common drafter intents — keep loose, drafter callers pass their own free-text
# intent if they want, this is just the well-known set.
INTENT_OUTREACH_COLD     = "outreach_cold"
INTENT_OUTREACH_WARM     = "outreach_warm"
INTENT_QUALIFIER         = "qualifier"
INTENT_OBJECTION_HANDLER = "objection_handler"
INTENT_BOOKING           = "booking"
INTENT_FOLLOWUP          = "followup"
INTENT_CHASE             = "chase"


def assemble_context(
    *,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
    intent: str = INTENT_OUTREACH_WARM,
    extra_context: Optional[dict] = None,
) -> dict:
    """Build the AI draft context for this client + intent.

    extra_context lets the caller inject ad-hoc fields (e.g. days_overdue,
    inquiry_text, contact_name) which get woven into the system prompt.
    """
    info = get_brief(client_id=client_id, client_name=client_name)
    if not info:
        return _minimal_safe_context(client_name, intent, extra_context)

    vertical = info.get("vertical") or "general"
    primer = get_primer(vertical) or {}
    brief = info.get("business_brief") or {}
    legacy = info.get("closer_brief") or {}

    merged = _merge(primer, brief, legacy)
    merged["client_name"] = info.get("client_name") or client_name or ""
    merged["vertical"] = vertical

    return {
        "client_name": merged["client_name"],
        "vertical": vertical,
        "tone": merged["tone"],
        "vocabulary": merged["vocabulary"],
        "guardrails": {
            "never_say": merged["never_say"],
            "compliance_notes": merged["compliance_notes"],
            "red_flags": merged["red_flags"],
        },
        "qualifying_questions": merged["qualifying_questions"],
        "closing_action": merged["closing_action"],
        "signature": merged["signature"],
        "system_prompt": _render_system_prompt(merged, intent, extra_context or {}),
    }


# ─── Internal ────────────────────────────────────────────────────────────────

def _merge(primer: dict, brief: dict, legacy: dict) -> dict:
    """Brief overrides primer; legacy closer_brief fills only where brief is empty."""
    def _first_nonempty(*values):
        for v in values:
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, (list, dict)) and v:
                return v
        return None

    return {
        "tone": (
            (brief.get("tone_overrides") or "").strip()
            or legacy.get("tone")
            or primer.get("default_tone")
            or "warm-professional"
        ),
        "vocabulary": list(primer.get("vocabulary") or []),
        "qualifying_questions": _first_nonempty(
            brief.get("qualifying_questions"),
            legacy.get("qualifying_questions"),
            primer.get("default_qualifying_questions"),
        ) or [],
        "closing_action": _first_nonempty(
            brief.get("closing_action"),
            legacy.get("closing_action"),
            primer.get("default_cta"),
        ) or "",
        "never_say": list(brief.get("never_say") or []) + list(legacy.get("never_say") or []) + list(primer.get("never_say_defaults") or []),
        "compliance_notes": list(primer.get("compliance_notes") or []),
        "red_flags": list(brief.get("red_flags") or []) + list(legacy.get("red_flags") or []),
        "products": brief.get("products") or ([{"name": legacy.get("product")}] if legacy.get("product") else []),
        "usps": brief.get("usps") or [],
        "icp": brief.get("icp") or legacy.get("icp") or "",
        "not_a_fit": brief.get("not_a_fit") or "",
        "signature": (
            (brief.get("signature") or "").strip()
            or _default_signature(brief)
        ),
        "one_liner": brief.get("one_liner") or "",
        "objection_responses": brief.get("objection_responses") or {},
        "always_say": brief.get("always_say") or [],
        "social_proof": brief.get("social_proof") or [],
        "geography": brief.get("geography") or [],
        "pricing_rules": brief.get("pricing_rules") or legacy.get("pricing_rules") or "",
        "calendar_link": brief.get("calendar_link") or "",
        "payment_terms": brief.get("payment_terms") or "",
    }


def _default_signature(brief: dict) -> str:
    name = (brief.get("trading_name") or "").strip()
    return f"— {name}" if name else ""


def _render_system_prompt(merged: dict, intent: str, extra: dict) -> str:
    """Compose a single system prompt the drafter can pass straight to Claude."""
    lines: list[str] = []

    name = merged.get("client_name") or "the business"
    one_liner = merged.get("one_liner")
    vertical = merged.get("vertical") or "general"

    lines.append(f"You are drafting on behalf of {name} ({vertical}).")
    if one_liner:
        lines.append(f"About them: {one_liner}")
    if merged.get("icp"):
        lines.append(f"Ideal customer: {merged['icp']}")
    if merged.get("not_a_fit"):
        lines.append(f"NOT a fit: {merged['not_a_fit']}")
    if merged.get("usps"):
        lines.append("Key strengths: " + "; ".join(merged["usps"][:5]))
    if merged.get("social_proof"):
        lines.append("Social proof you may reference: " + "; ".join(merged["social_proof"][:3]))
    if merged.get("geography"):
        lines.append("Geography: " + ", ".join(merged["geography"]))

    lines.append(f"Voice: {merged['tone']}.")
    if merged.get("vocabulary"):
        lines.append("Industry vocabulary you may use: " + ", ".join(merged["vocabulary"][:15]) + ".")

    guard = merged.get("never_say") or []
    if guard:
        lines.append("Never say (banned phrasing): " + "; ".join(guard[:10]) + ".")
    compliance = merged.get("compliance_notes") or []
    if compliance:
        lines.append("Compliance: " + " | ".join(compliance) + ".")
    always_say = merged.get("always_say") or []
    if always_say:
        lines.append("Reinforce these phrases when natural: " + "; ".join(always_say[:5]) + ".")

    # Intent-specific tail
    intent_line = _intent_directive(intent, merged, extra)
    if intent_line:
        lines.append(intent_line)

    if merged.get("closing_action"):
        lines.append(f"The desired next step is: {merged['closing_action']}.")

    if merged.get("signature"):
        lines.append(f"Sign off with: {merged['signature']}")

    lines.append("Keep messages short, conversational, WhatsApp-shaped (under 60 words).")
    lines.append("Never invent facts. If something is unknown, ask rather than assume.")

    return "\n".join(lines)


def _intent_directive(intent: str, merged: dict, extra: dict) -> str:
    qq = merged.get("qualifying_questions") or []

    if intent == INTENT_OUTREACH_COLD:
        return (
            "Goal: open a warm, low-pressure first contact. Reference how you got their details. "
            "Do not pitch hard. End with a soft question that invites a reply."
        )
    if intent == INTENT_OUTREACH_WARM:
        return (
            "Goal: re-engage someone who has shown prior interest or is in the client's existing list. "
            "Acknowledge the prior context if available, then move toward the next step."
        )
    if intent == INTENT_QUALIFIER:
        if qq:
            return f"Goal: ask one of these qualifying questions, picked to fit the conversation: {' | '.join(qq[:5])}"
        return "Goal: ask one qualifying question that fits the conversation so far."
    if intent == INTENT_OBJECTION_HANDLER:
        last = (extra.get("objection") or "").strip()
        responses = merged.get("objection_responses") or {}
        crafted = responses.get(last) if last else ""
        if crafted:
            return f"Goal: address the objection '{last}'. Lean on this response style: {crafted}"
        return "Goal: address the customer's objection directly without dismissing it. Acknowledge, then re-frame."
    if intent == INTENT_BOOKING:
        cal = merged.get("calendar_link")
        if cal:
            return f"Goal: book the next step. Offer a specific time and include the booking link: {cal}"
        return "Goal: book the next step. Offer two specific time options."
    if intent == INTENT_FOLLOWUP:
        return (
            "Goal: gentle follow-up on a previous message that didn't get a reply. Keep it brief. "
            "Add one new piece of value or context — never just 'bumping this'."
        )
    if intent == INTENT_CHASE:
        days = extra.get("days_overdue")
        amount = extra.get("amount_ngn")
        if days is not None or amount is not None:
            return f"Goal: chase a payment that is overdue ({days} days, ₦{amount:,} if known). Stay firm but professional."
        return "Goal: chase a payment that is overdue. Stay firm but professional."
    return f"Goal: {intent}."


def _minimal_safe_context(client_name: Optional[str], intent: str, extra: Optional[dict]) -> dict:
    name = client_name or "the business"
    return {
        "client_name": client_name or "",
        "vertical": "general",
        "tone": "warm-professional",
        "vocabulary": [],
        "guardrails": {"never_say": [], "compliance_notes": [], "red_flags": []},
        "qualifying_questions": [],
        "closing_action": "",
        "signature": "",
        "system_prompt": (
            f"You are drafting on behalf of {name}.\n"
            "Voice: warm-professional. Keep it short, WhatsApp-shaped (under 60 words).\n"
            f"Goal: {intent}. Never invent facts."
        ),
    }
