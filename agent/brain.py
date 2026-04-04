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
    enrichment_context: Optional[str] = None,   # from tools.enrichment.format_enrichment_for_prompt
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

    enrichment_block = f"\n{enrichment_context}" if enrichment_context else ""

    user_prompt = f"""
Write a {channel} outreach message for the following business.

Business name: {business_name}
Location: {location_hint or address or "Lagos"}
Category: {category or "Not specified"}
Google rating: {rating or "Unknown"}
Website: {website or "None found"}
Channel: {channel}
{enrichment_block}
{followup_note}

Return ONLY:
- For WhatsApp: the message text (max 4 sentences, no subject line)
- For Email: JSON with keys "subject" and "message" (max 6 sentence body)

If website intelligence is provided above, reference at least one specific detail in the message.
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


# ─── B2C message generation ──────────────────────────────────────────────────

def generate_b2c_message(
    customer_name: str,
    channel: str,               # "whatsapp" | "email"
    vertical: str,
    client_brief: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """
    Generate a personalized B2C outreach message for a customer.
    Uses client brief + customer notes/tags for personalization.
    Returns {"message": str} for WhatsApp or {"subject": str, "message": str} for email.
    """
    system = _load_prompt("system.txt")

    brief_block = f"\nClient context: {client_brief}" if client_brief else ""
    notes_block  = f"\nCustomer notes: {notes}" if notes else ""
    tags_block   = f"\nCustomer tags/segments: {', '.join(tags)}" if tags else ""

    user_prompt = f"""
Write a {channel} message to a customer on behalf of a business.

Customer name: {customer_name}
Channel: {channel}
{brief_block}
{notes_block}
{tags_block}

This is a B2C message — warm, personal, conversational. Not a cold sales pitch.
Reference the customer's name. Keep it friendly and to the point.

Return ONLY:
- For WhatsApp: the message text (max 4 sentences, no subject line)
- For Email: JSON with keys "subject" and "message" (max 6 sentence body)

No explanations. No preamble. Just the message.
"""

    import json
    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    if channel == "email":
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            return {"subject": f"A message for you, {customer_name}", "message": raw}

    return {"message": raw}


# ─── Invoice reminder generation ─────────────────────────────────────────────

def generate_invoice_reminder(
    client_name: str,
    debtor_name: str,
    amount_ngn: float,
    description: str,
    days_overdue: int,
    tone: str,           # polite | firm | payment_plan | final
    reminder_count: int,
) -> str:
    """
    Generate a WhatsApp invoice reminder message.
    Escalates in tone based on how overdue the invoice is.
    """
    tone_instructions = {
        "polite": "Friendly and warm. Assume it was an oversight. No pressure. One short paragraph.",
        "firm": "Professional and direct. Remind them the invoice is overdue. Request payment within 48 hours.",
        "payment_plan": "Empathetic but firm. Offer a flexible payment plan — suggest paying in 2 instalments. Make it easy to say yes.",
        "final": "Serious and final. This is the last reminder before the matter is escalated. Do not threaten legally — just say this is the final notice.",
    }

    amount_formatted = f"₦{amount_ngn:,.0f}"

    user_prompt = f"""
Write a WhatsApp message from {client_name} to {debtor_name} requesting payment of an overdue invoice.

Invoice details:
- Amount: {amount_formatted}
- Description: {description or "Services rendered"}
- Days overdue: {days_overdue}
- Reminder number: {reminder_count + 1}
- Tone: {tone_instructions.get(tone, tone_instructions["polite"])}

Rules:
- Write in first person as {client_name}
- Keep it under 5 sentences
- Include the amount prominently
- Do NOT use aggressive or threatening language
- Sound human, not automated
- No subject line — this is WhatsApp

Return ONLY the message text. No preamble.
"""

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


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


def classify_reply(reply_text: str, business_name: str, vertical: str) -> dict:
    """
    Classify an inbound reply using Claude Haiku (fast + cheap).
    Returns intent, urgency, and a one-line summary.
    """
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                f"Classify this reply from a Lagos business owner. Vertical: {vertical}. "
                f"Business: {business_name}.\n\nReply: \"{reply_text}\"\n\n"
                "Return JSON only:\n"
                "{\n"
                "  \"intent\": \"interested\" | \"not_now\" | \"opted_out\" | \"referral\" | \"question\" | \"unknown\",\n"
                "  \"urgency\": \"high\" | \"medium\" | \"low\",\n"
                "  \"summary\": \"one sentence max\"\n"
                "}"
            ),
        }],
    )

    import json
    raw = response.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        log.warning("classify_reply_parse_failed", raw=raw)
        return {"intent": "unknown", "urgency": "low", "summary": reply_text[:100]}


def generate_outreach_message_for_client(
    vertical: str,
    business_name: str,
    channel: str,
    client_context: str,
    address: Optional[str] = None,
    category: Optional[str] = None,
    rating: Optional[float] = None,
    website: Optional[str] = None,
    is_followup: bool = False,
    attempt_number: int = 1,
) -> dict:
    """
    Generate a message using a client-specific context prompt instead of the
    generic vertical prompt. Used when a ReachNG client has a custom brief.
    """
    system = _load_prompt("system.txt")

    location_hint = ""
    if address:
        for area in ["Victoria Island", "Lekki", "Ikoyi", "Ajah", "Chevron",
                     "Ikeja", "Surulere", "Yaba", "Lagos Island"]:
            if area.lower() in address.lower():
                location_hint = area
                break

    followup_note = ""
    if is_followup:
        followup_note = f"\n\nIMPORTANT: This is follow-up attempt {attempt_number}. Acknowledge you reached out before. Keep it very brief and low pressure."

    user_prompt = f"""
Write a {channel} outreach message for the following business on behalf of our client.

CLIENT BRIEF:
{client_context}

TARGET BUSINESS:
Name: {business_name}
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

    client_api = _get_client()
    response = client_api.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    if channel == "email":
        import json
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            log.warning("client_email_parse_failed", raw=raw)
            return {"subject": f"Quick question for {business_name}", "message": raw}

    return {"message": raw}


def generate_social_outreach_message(
    vertical: str,
    business_name: str,
    channel: str,
    platform: str,
    post_text: str,
    profile_url: str = "",
    address: Optional[str] = None,
) -> dict:
    """
    Generate a personalised message that references the contact's actual post.
    Opens 10x better than cold outreach — they've already signalled intent.
    """
    system = _load_prompt("system.txt")
    vertical_context = _load_prompt(f"{vertical}.txt")

    platform_label = {"instagram": "Instagram", "twitter": "Twitter/X", "facebook": "Facebook"}.get(platform, platform)

    user_prompt = f"""
Write a {channel} outreach message for a Lagos business we discovered on {platform_label}.

IMPORTANT: Their post is the reason we're reaching out. Reference it naturally — don't be creepy, be relevant.
The opener should feel like "I came across your post..." or "Saw you're [doing X]..." — warm, not salesy.

Business name: {business_name}
Platform: {platform_label}
Their post / bio text:
\"\"\"{post_text}\"\"\"
Profile: {profile_url or "N/A"}
Location: {address or "Lagos"}
Channel: {channel}

Return ONLY:
- For WhatsApp: the message text (max 4 sentences — reference the post, offer value, soft CTA)
- For Email: JSON with keys "subject" and "message" (subject should reference their post context, max 6 sentence body)

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
        import json
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            log.warning("social_email_parse_failed", raw=raw)
            return {"subject": f"Saw your post about {vertical.replace('_', ' ')} — quick question", "message": raw}

    return {"message": raw}


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
