"""
ReachNG self-outreach drafter — for Yori's own SDR campaign.

Sits outside the standard agent/brain.py vertical drafters because the
voice + framing are completely different: we're writing AS the founder,
not AS the agent.

Pipeline:
  1. discover_businesses() finds Lagos/Abuja SMEs via Maps Places
  2. lean_scraper + email_finder enrich with email + decision-maker
  3. draft_outreach_email() produces {subject, message} via Haiku
  4. attach_landing_link() injects the UTM-tagged reachng.ng link below
     the sign-off — guaranteed, never trusted to the LLM
  5. queue_draft() puts it in HITL — Yori approves every send for first 50

Cost: ~₦4 per draft (Haiku ~600 tokens out). 100 sends ≈ ₦400 total.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import anthropic
import structlog

from config import get_settings

log = structlog.get_logger()


_ROOT = Path(__file__).resolve().parent.parent
_PROMPT_PATH = _ROOT / "agent" / "prompts" / "reachng_outreach.txt"
_NG_CTX_PATH = _ROOT / "agent" / "prompts" / "_nigerian_context.txt"

_LANDING_BASE = "https://www.reachng.ng"


# ── A/B/C variant angles ─────────────────────────────────────────────────────
# Three angles on the SAME founder intro email (same hard constraints, length,
# signature, no-false-claims rules). The directive only steers which pain the
# email leads with. Letters map to tools.ab_testing.VARIANTS so the runner can
# record which angle each prospect got and compare reply rates later.
VARIANT_STYLES: dict[str, str] = {
    "A": "founder",
    "B": "money_leak",
    "C": "owner_relief",
}

_STYLE_DIRECTIVES: dict[str, str] = {
    "founder": (
        "VARIANT ANGLE: FOUNDER / DIRECT.\n"
        "Lead as the founder making a genuine early-access invitation. The reason-"
        "for-writing sentence should make clear you're inviting a few premium "
        "businesses in their city to try the early version before launch. Tone: "
        "respectful peer-to-peer, not a pitch. Seed tone (do NOT copy verbatim, "
        "rewrite as a proper email): \"I'm building ReachNG, a digital employee "
        "for WhatsApp. I'm inviting a few premium {vertical} businesses in {city} to "
        "try the early version. Worth showing you a 2-minute demo?\""
    ),
    "money_leak": (
        "VARIANT ANGLE: MONEY-LEAK.\n"
        "Lead with money quietly dying in WhatsApp chats: missed price enquiries, "
        "unpaid follow-ups, slow replies, unconfirmed transfer receipts. Frame the "
        "two capabilities you pick around catching those leaks. Do NOT invent "
        "figures or promise recovered revenue. Seed tone (rewrite, don't copy): "
        "\"I'm building ReachNG to help businesses spot money dying in WhatsApp "
        "chats, missed enquiries, unpaid follow-ups, slow replies. I'm testing it "
        "with a few premium {vertical} businesses before launch.\""
    ),
    "owner_relief": (
        "VARIANT ANGLE: OWNER-RELIEF.\n"
        "Lead with relief for a busy owner: EYO watches WhatsApp, drafts replies in "
        "their voice, and sends a daily brief of what needs attention, every reply "
        "still waiting for their tap. Frame it as taking weight off the owner. Seed "
        "tone (rewrite, don't copy): \"ReachNG is a digital employee that watches "
        "WhatsApp, drafts replies in your voice, and sends the owner a daily brief. "
        "Built for busy Nigerian SMEs. Onboarding a few early partners before launch.\""
    ),
}


def _style_directive(variant: Optional[str]) -> str:
    """Resolve a variant letter (A/B/C) to its angle directive. Unknown/none → ''."""
    if not variant:
        return ""
    style = VARIANT_STYLES.get(variant.upper())
    return _STYLE_DIRECTIVES.get(style or "", "")


def _load_system_prompt() -> str:
    base = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else ""
    ctx  = _NG_CTX_PATH.read_text(encoding="utf-8") if _NG_CTX_PATH.exists() else ""
    return (ctx + "\n\n" + base).strip()


def _build_user_block(*, business_name: str, vertical: str,
                       address: Optional[str], category: Optional[str],
                       rating: Optional[float], reviews_excerpt: Optional[str],
                       contact_name: Optional[str], contact_title: Optional[str],
                       website: Optional[str]) -> str:
    lines = [
        f"Business: {business_name}",
        f"Vertical (internal label): {vertical}",
    ]
    if contact_name:
        lines.append(f"Decision-maker: {contact_name}" + (f", {contact_title}" if contact_title else ""))
    if address:
        lines.append(f"Address: {address}")
    if category:
        lines.append(f"Category: {category}")
    if rating is not None:
        lines.append(f"Maps rating: {rating}")
    if reviews_excerpt:
        lines.append(f"Recent review excerpt: \"{reviews_excerpt[:200]}\"")
    if website:
        lines.append(f"Website: {website}")
    lines.append("")
    lines.append("Draft the cold-outreach email per the system rules. "
                  "Return ONLY the JSON object — no preamble, no fences.")
    return "\n".join(lines)


def draft_outreach_email(
    *,
    business_name: str,
    vertical: str = "general",
    address: Optional[str] = None,
    category: Optional[str] = None,
    rating: Optional[float] = None,
    reviews_excerpt: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_title: Optional[str] = None,
    website: Optional[str] = None,
    variant: Optional[str] = None,
) -> dict:
    """
    Returns {"subject": str, "message": str} for the cold first-touch email.

    `variant` (A/B/C) selects the angle the email leads with (see VARIANT_STYLES);
    None falls back to the neutral founder intro. Throws if the model produces
    unparseable output — the caller should skip this prospect and log, never
    send the broken draft.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = _load_system_prompt()
    user_block = _build_user_block(
        business_name=business_name, vertical=vertical,
        address=address, category=category, rating=rating,
        reviews_excerpt=reviews_excerpt,
        contact_name=contact_name, contact_title=contact_title,
        website=website,
    )
    directive = _style_directive(variant)
    if directive:
        user_block = f"{directive}\n\n{user_block}"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        temperature=0.6,
        system=system_prompt,
        messages=[{"role": "user", "content": user_block}],
    )
    raw = "".join(b.text for b in resp.content
                   if getattr(b, "type", None) == "text").strip()

    # Tolerate ``` fences and stray prose
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.S)
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            raw = m.group(0)

    try:
        data = json.loads(raw)
    except Exception as e:
        log.error("reachng_outreach_parse_failed", error=str(e), raw=raw[:200])
        raise RuntimeError(f"could not parse draft: {e}")

    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    if not subject or not message:
        raise RuntimeError("draft missing subject or body")

    # Tone scrub at the boundary (same rule as every other ReachNG send)
    try:
        from tools.tone import scrub_endearments
        subject = scrub_endearments(subject)
        message = scrub_endearments(message)
    except Exception:
        pass

    # Em-dash / en-dash scrub — these are the AI-smell tell. Replace with the
    # right ASCII punctuation depending on context. Spaced ' — ' becomes ', '
    # (parenthetical), bare '—' becomes ',', '–' (en-dash) used in ranges
    # becomes '-', and '…' ellipsis collapses to '.'.
    subject = _scrub_dashes(subject)
    message = _scrub_dashes(message)

    return {"subject": subject, "message": message}


def _scrub_dashes(text: str) -> str:
    """Remove AI-smell punctuation. Numeric ranges (110–150) become hyphenated
    (110-150); spaced em/en dashes become commas; lingering bare dashes become
    commas; ellipses become periods."""
    if not text:
        return text
    # Numeric range first: keep as ASCII hyphen, no spaces (e.g. 110–150 → 110-150)
    text = re.sub(r"(\d)\s*[—–]\s*(\d)", r"\1-\2", text)
    # Spaced em/en dash between words → comma + space
    text = re.sub(r"\s+[—–]\s+", ", ", text)
    # Any remaining bare em/en dash → comma
    text = text.replace("—", ",").replace("–", ",")
    # Collapse accidental double commas
    text = re.sub(r",\s*,", ",", text)
    # Ellipsis → period
    text = text.replace("…", ".")
    # Collapse multi-space artifacts
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def attach_landing_link(
    message: str,
    *,
    vertical: str = "general",
    contact_id: Optional[str] = None,
    path: str = "/",
    prospect_profile: Optional[dict] = None,
) -> str:
    """
    Two-link CTA:
      - Plain `www.reachng.ng` lives in the signature (trust signal). Anyone
        forwarding the email or typing it in by hand gets there cleanly.
      - A personalised short link `www.reachng.ng/hi/{slug}` lives in a P.S.
        line. When the recipient taps it, the landing page knows who they
        are and pre-fills their business name, vertical, and forms — no
        retyping. Strangers who landed via the plain URL just see the
        generic landing.

    `prospect_profile` is what gets stored against the slug:
        {business_name, contact_name, first_name, vertical, category}
    The /hi/{slug} handler reads this and sets a 24h cookie.
    """
    body = (message or "").rstrip()
    # Strip any URL the LLM tried to add despite the rule
    body = re.sub(r"https?://\S+", "", body).rstrip()
    body = re.sub(r"www\.reachng\.ng\S*", "www.reachng.ng", body)

    # Mint a personalised short link. Fail-safe: if Mongo is down or minting
    # errors, the email still ships with the plain URL in the signature.
    try:
        from services.outreach_links import mint as _mint_slug
        slug = _mint_slug(
            target_url="/",
            vertical=vertical,
            contact_id=contact_id,
            variant="hi",
            prospect_profile=prospect_profile or {"vertical": vertical},
        )
        return f"{body}\n\nP.S. www.reachng.ng/hi/{slug} — one-tap, takes you straight to a demo set up for you."
    except Exception as e:
        log.info("personal_link_mint_failed_falling_back", error=str(e))
        return body


# ── End-to-end convenience: draft + inject in one call ─────────────────────

def draft_with_link(
    *,
    business_name: str,
    contact_id: Optional[str] = None,
    vertical: str = "general",
    variant: Optional[str] = None,
    **fields,
) -> dict:
    """Single entry-point used by the campaign runner.

    Builds the prospect_profile that backs the /hi/{slug} personalisation
    from the enrichment fields we already have, so the landing page can
    pre-fill the recipient's business name, vertical, and forms.

    `variant` (A/B/C) picks the angle; it's echoed back on the result so the
    runner can record it for A/B/C reply-rate tracking.
    """
    out = draft_outreach_email(business_name=business_name, vertical=vertical,
                               variant=variant, **fields)

    contact_name = fields.get("contact_name") or ""
    first_name   = contact_name.strip().split()[0] if contact_name else ""
    prospect_profile = {
        "business_name": business_name,
        "contact_name":  contact_name or None,
        "first_name":    first_name or None,
        "vertical":      vertical,
        "category":      fields.get("category"),
        "address":       fields.get("address"),
    }
    # Drop empty values so the cookie payload stays tight
    prospect_profile = {k: v for k, v in prospect_profile.items() if v}

    out["message"] = attach_landing_link(
        out["message"],
        vertical=vertical,
        contact_id=contact_id,
        prospect_profile=prospect_profile,
    )
    if variant:
        out["variant"] = variant.upper()
        out["variant_style"] = VARIANT_STYLES.get(variant.upper())
    return out
