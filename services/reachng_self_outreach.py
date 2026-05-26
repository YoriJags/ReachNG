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
) -> dict:
    """
    Returns {"subject": str, "message": str} for the cold first-touch email.

    Throws if the model produces unparseable output — the caller should skip
    this prospect and log, never send the broken draft.
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
) -> str:
    """
    Append a clean CTA block with TWO visible links:
      - The main landing URL (so the recipient can see we exist as a company)
      - A direct link to the Try-EYO sandbox at /#try (the actual demo)

    Why post-draft injection: the LLM drops or mangles URLs. The link is
    the entire CTA — it cannot be flaky.

    Uses real UTM keys (utm_source / utm_medium / utm_campaign). Without
    them, the `/` route redirects to the /start cover page. UTM-tagged
    arrivals land directly on the landing, which is what a recipient
    expects.

    Extra params: v=<vertical>, c=<contact_id> for PostHog attribution.
    """
    params = {
        "utm_source":   "email",
        "utm_medium":   "outreach",
        "utm_campaign": "founder_cohort",
        "v":            vertical,
    }
    if contact_id:
        params["c"] = str(contact_id)

    qs            = urlencode(params)
    full_site_url = f"{_LANDING_BASE}{path}?{qs}"
    full_try_url  = f"{_LANDING_BASE}/?{qs}#try"   # anchor onto the Try-EYO widget

    # Mint clean short slugs so the email never shows the raw UTM string.
    # /o/{slug} resolves server-side to the real UTM-tagged URL.
    try:
        from services.outreach_links import mint as _mint_slug
        site_slug = _mint_slug(target_url=full_site_url, vertical=vertical,
                                contact_id=contact_id, variant="site")
        try_slug  = _mint_slug(target_url=full_try_url,  vertical=vertical,
                                contact_id=contact_id, variant="try")
        site_url = f"{_LANDING_BASE}/o/{site_slug}"
        try_url  = f"{_LANDING_BASE}/o/{try_slug}"
    except Exception:
        # If minting fails (Mongo down, etc), fall back to the long URLs so
        # the email is still functional. Not ideal, but better than no link.
        site_url = full_site_url
        try_url  = full_try_url

    body = (message or "").rstrip()
    # Strip any URL the LLM tried to add despite the rule
    body = re.sub(r"https?://\S+", "", body).rstrip()

    cta = (
        f"\n\n---\n"
        f"Site: {site_url}\n"
        f"Try EYO live (no signup): {try_url}"
    )
    return body + cta


# ── End-to-end convenience: draft + inject in one call ─────────────────────

def draft_with_link(
    *,
    business_name: str,
    contact_id: Optional[str] = None,
    vertical: str = "general",
    **fields,
) -> dict:
    """Single entry-point used by the campaign runner."""
    out = draft_outreach_email(business_name=business_name, vertical=vertical, **fields)
    out["message"] = attach_landing_link(
        out["message"], vertical=vertical, contact_id=contact_id,
    )
    return out
