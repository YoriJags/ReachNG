"""
Claude agent brain — orchestrates discovery, message writing, and outreach decisions.
Uses the Anthropic API directly for message generation.
The FastMCP server exposes tools that Claude calls during agentic runs.
"""
import anthropic
from pathlib import Path
from typing import Optional
from config import get_settings
import structlog

log = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


# ─── Message generation ───────────────────────────────────────────────────────

def generate_outreach_message(
    vertical: str,
    business_name: str,
    channel: str,               # "whatsapp" | "email"
    address: Optional[str] = None,
    category: Optional[str] = None,
    rating: Optional[float] = None,
    website: Optional[str] = None,
    is_followup: bool = False,
    attempt_number: int = 1,
) -> dict:
    """
    Generate a personalised outreach message for a business.
    Returns {"message": str} for WhatsApp, or {"subject": str, "message": str} for email.
    """
    system = _load_prompt("system.txt")
    vertical_context = _load_prompt(f"{vertical}.txt")

    location_hint = ""
    if address:
        # Extract neighbourhood from address (e.g. "Victoria Island" from full address)
        for area in ["Victoria Island", "Lekki", "Ikoyi", "Ajah", "Chevron",
                     "Ikeja", "Surulere", "Yaba", "Lagos Island"]:
            if area.lower() in address.lower():
                location_hint = area
                break

    followup_note = ""
    if is_followup:
        followup_note = f"\n\nIMPORTANT: This is follow-up attempt {attempt_number}. Acknowledge you reached out before. Keep it very brief and low pressure."

    user_prompt = f"""
Write a {channel} outreach message for the following business.

Business name: {business_name}
Location: {location_hint or address or "Lagos"}
Category: {category or "Not specified"}
Google rating: {rating or "Unknown"}
Website: {website or "None found"}
Channel: {channel}
{followup_note}

Return ONLY:
- For WhatsApp: the message text (max 4 sentences, no subject line)
- For Email: JSON with keys "subject" and "message" (max 6 sentence body)

No explanations. No preamble. Just the message.
"""

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=f"{system}\n\n{vertical_context}",
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    if channel == "email":
        # Parse JSON response
        import json
        try:
            # Handle potential markdown code fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            log.warning("email_parse_failed", raw=raw)
            # Fallback: use raw as message with generic subject
            return {"subject": f"Quick question for {business_name}", "message": raw}

    return {"message": raw}


# ─── Campaign decision making ─────────────────────────────────────────────────

def should_contact(
    business_name: str,
    vertical: str,
    rating: Optional[float],
    has_phone: bool,
    has_website: bool,
) -> bool:
    """
    Simple rule-based filter — no Claude API call needed.
    Save Claude tokens for message generation only.
    """
    # Must have at least one contact channel
    if not has_phone and not has_website:
        return False

    # Skip very low rated businesses — bad signal
    if rating is not None and rating < 2.5:
        return False

    return True


def generate_campaign_summary(stats: dict, vertical: str) -> str:
    """Generate a plain-English campaign summary for the dashboard."""
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Summarise this outreach campaign stats in 2 sentences for a business dashboard. "
                f"Vertical: {vertical}. Stats: {stats}. Be direct and data-focused."
            )
        }],
    )
    return response.content[0].text.strip()
