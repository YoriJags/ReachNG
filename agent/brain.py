"""
Claude agent brain — orchestrates discovery, message writing, and outreach decisions.
Uses the Anthropic API directly for message generation.
The FastMCP server exposes tools that Claude calls during agentic runs.
"""
import anthropic
import json as _json
from pathlib import Path
from typing import Optional
from config import get_settings
import structlog

log = structlog.get_logger()

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        log.warning("prompt_file_missing", filename=filename)
        return ""
    return path.read_text(encoding="utf-8")


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
    from services.brief.verticals import vertical_extras, vertical_pitch_mode

    system = _load_prompt("system.txt")
    self_brief = _load_prompt("self_brief.txt")
    vertical_context = _load_prompt(f"{vertical}.txt")

    # Pitch framing depends on whether the vertical is inbound-driven (close their
    # existing leads) or operations-driven (free their team from back-office work).
    pitch_mode = vertical_pitch_mode(vertical)
    if pitch_mode == "workload_removal":
        framing_rule = (
            "\n\nPITCH FRAMING FOR THIS VERTICAL — workload_removal.\n"
            "This business is itself in the sales business OR runs heavy ops. "
            "Their 'leads' are long-cycle B2B relationships, not WhatsApp DMs to convert. "
            "Do NOT pitch 'we close your inbound leads' — it's insulting and irrelevant. "
            "Instead, lead with WORKLOAD REMOVAL: we run the operational back-office "
            "(payroll, contributions, dispatch, compliance ops, whatever fits) so their "
            "team gets back to what they actually do (BD, sourcing, delivery). "
            "Frame the agent as a back-office hire, not a salesperson."
        )
    else:
        framing_rule = (
            "\n\nPITCH FRAMING FOR THIS VERTICAL — inbound_closer.\n"
            "Lead with: 'we close the inbound leads you already have' — DMs, walk-ins, "
            "form fills, referrals. Frame the agent as the AI sales operator that drafts "
            "every reply, qualifies, follows up, and books the action — all from their "
            "own WhatsApp number, all human-approved. Never claim we generate new leads."
        )

    # Vertical-matched operational suite — mention as 'and-also', not the headline.
    extras_blurb = vertical_extras(vertical)
    extras_rule = (
        f"\n\nOPERATIONAL EXTRAS FOR THIS VERTICAL: {extras_blurb}.\n"
        "If — and only if — the prospect's profile clearly fits this vertical, "
        "you MAY mention these once near the end as 'included, no extra fee.' "
        "Never lead with them. Never bullet-list them. The framing rule above "
        "is always the headline."
        if extras_blurb else
        "\n\nNo additional operational extras ship for this vertical yet. "
        "Stick to the framing rule above — do NOT promise back-office modules."
    )

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

    channel_guide = (
        "WHATSAPP RULES:\n"
        "- Casual, warm, direct. Voice-message energy — like a founder texting a peer.\n"
        "- Max 4 short sentences. No bullet points, no headers, no formal sign-off.\n"
        "- Start with the business name or a quick observation. Skip pleasantries.\n"
        "- End with a single low-pressure question or a soft CTA.\n"
        "- Return plain text only. No subject line."
        if channel == "whatsapp" else
        "EMAIL RULES:\n"
        "- Professional but warm. Think well-written cold email, not a newsletter.\n"
        "- Subject line: punchy, specific, < 50 chars — NO clickbait.\n"
        "- Opening line: a genuine, specific observation about their business (1 sentence).\n"
        "- Body: 2-3 sentences max explaining the value. No bullet lists.\n"
        "- Closing: one clear CTA — a question or a link to book a call.\n"
        "- Sign off with 'Best,' and leave a placeholder name.\n"
        "- Return JSON with keys 'subject' and 'message' (message = full email body, plain text)."
    )

    user_prompt = f"""
Write a {channel} outreach message for the following business.

Business name: {business_name}
Location: {location_hint or address or "Lagos"}
Category: {category or "Not specified"}
Google rating: {rating or "Unknown"}
Website: {website or "None found"}
{enrichment_block}
{followup_note}

{channel_guide}

CRITICAL: Never use placeholder text like [Partner Name], [Name], [Contact], [First Name], or any bracket-enclosed variable. If you do not know the contact's name, address them as "there" or use the business name directly. Never leave any placeholder unresolved.

If website intelligence is provided above, reference at least one specific detail in the message.
No explanations. No preamble. Just the message.
"""

    client = _get_client()
    # Layer order: ReachNG self-brief (voice) → vertical pitch primer (what we
    # know about their industry) → base system prompt. All three get sent so
    # Claude has a full picture before drafting.
    layered_system = (
        f"{self_brief}\n\n{vertical_context}{framing_rule}{extras_rule}\n\n{system}"
        if self_brief else
        f"{system}\n\n{vertical_context}{framing_rule}{extras_rule}"
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=layered_system,
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
    client_brief: Optional[str] = None,    # legacy free-text brief — used only as a fallback
    client_name: Optional[str] = None,     # PREFERRED — looks up structured BusinessBrief
    notes: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """
    Generate a personalized B2C outreach message for a customer.

    When `client_name` is supplied, the system prompt is composed from the
    structured BusinessBrief + vertical primer via assemble_context().
    Otherwise we fall back to the loose free-text `client_brief` for back-compat.
    Returns {"message": str} for WhatsApp or {"subject": str, "message": str} for email.
    """
    base_system = _load_prompt("system.txt")

    # Prefer the structured brief context when we know the client.
    brief_system: Optional[str] = None
    if client_name:
        try:
            from services.brief import assemble_context
            ctx = assemble_context(client_name=client_name, intent="outreach_warm")
            brief_system = ctx.get("system_prompt")
        except Exception as exc:
            log.warning("brief_context_fetch_failed", client=client_name, error=str(exc))

    system = (brief_system + "\n\n" + base_system) if brief_system else base_system

    notes_block = f"\nCustomer notes: {notes}" if notes else ""
    tags_block  = f"\nCustomer tags/segments: {', '.join(tags)}" if tags else ""
    fallback_brief_block = ""
    if not brief_system and client_brief:
        fallback_brief_block = f"\nClient context: {client_brief}"

    user_prompt = f"""
Write a {channel} message to a customer on behalf of {client_name or "the business"}.

Customer name: {customer_name}
Channel: {channel}
{fallback_brief_block}
{notes_block}
{tags_block}

This is a B2C message — warm, personal, conversational. Not a cold sales pitch.
Reference the customer's name. Keep it friendly and to the point.
Stay strictly within the voice, vocabulary, and never-say constraints described in the system prompt.

Return ONLY:
- For WhatsApp: the message text (max 4 sentences, no subject line)
- For Email: JSON with keys "subject" and "message" (max 6 sentence body)

No explanations. No preamble. Just the message.
"""

    import json
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
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

    # Pull the structured BusinessBrief if we know the creditor — chasers benefit
    # from the same tone/never-say guardrails as outreach (warn-only on thin briefs).
    brief_system: Optional[str] = None
    try:
        from services.brief import assemble_context
        ctx = assemble_context(
            client_name=client_name,
            intent="chase",
            extra_context={"days_overdue": days_overdue, "amount_ngn": amount_ngn},
        )
        brief_system = ctx.get("system_prompt")
    except Exception as exc:
        log.warning("brief_context_fetch_failed_invoice", client=client_name, error=str(exc))

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=brief_system if brief_system else anthropic.NOT_GIVEN,
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


def classify_reply(
    reply_text: str,
    business_name: str,
    vertical: str,
    market: str = "Nigeria",
) -> dict:
    """
    Classify an inbound reply using Claude Haiku (fast + cheap).

    Returns:
        intent:           interested | not_now | opted_out | referral | question | unknown
        urgency:          high | medium | low
        budget_authority: high | medium | low | unknown
            — "high" means they sound like a decision-maker ready to spend
        hot_lead:         bool — True when intent=interested AND budget_authority=high
        summary:          one-line summary of what they said
    """
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Classify this reply from a business owner. "
                f"Market: {market}. Vertical: {vertical}. Business: {business_name}.\n\n"
                f"Reply: \"{reply_text}\"\n\n"
                "Opt-out signals (any of these = opted_out): "
                "Stop, Remove me, Unsubscribe, Not interested, Please don't contact, "
                "Take me off, Don't message me, Wrong number.\n\n"
                "Hot lead signals: mentions budget, asks for pricing/proposal/meeting, "
                "says 'when can we talk', 'send me more info', 'we've been looking for this'.\n\n"
                "Return JSON only:\n"
                "{\n"
                "  \"intent\": \"interested\" | \"not_now\" | \"opted_out\" | \"referral\" | \"question\" | \"unknown\",\n"
                "  \"urgency\": \"high\" | \"medium\" | \"low\",\n"
                "  \"budget_authority\": \"high\" | \"medium\" | \"low\" | \"unknown\",\n"
                "  \"hot_lead\": true | false,\n"
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
        result = json.loads(raw.strip())
        # Derive hot_lead if Claude didn't return it
        if "hot_lead" not in result:
            result["hot_lead"] = (
                result.get("intent") == "interested" and
                result.get("budget_authority") in ("high", "medium")
            )
        return result
    except Exception:
        log.warning("classify_reply_parse_failed", raw=raw)
        return {
            "intent": "unknown", "urgency": "low",
            "budget_authority": "unknown", "hot_lead": False,
            "summary": reply_text[:100],
        }


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


def extract_with_gemini(prompt: str, text: str) -> str:
    """
    Use Gemini Flash for cheap, fast extraction tasks.
    Falls back to Claude Haiku if Gemini API key not configured.
    Use this for: PDF data extraction, lead categorisation, bulk text parsing.
    NOT for: outreach message writing (use Claude Sonnet for that).
    """
    settings = get_settings()
    gemini_key = settings.gemini_api_key

    if gemini_key:
        try:
            import httpx
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                json={
                    "contents": [{"parts": [{"text": f"{prompt}\n\n{text}"}]}],
                    "generationConfig": {"maxOutputTokens": 500, "temperature": 0.1},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning("gemini_extraction_failed", error=str(e), fallback="haiku")

    # Fallback: Claude Haiku
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": f"{prompt}\n\n{text}"}],
    )
    return response.content[0].text.strip()


def extract_invoice_fields(pdf_text: str) -> dict:
    """
    Extract structured invoice data from raw PDF text using Gemini Flash.
    Returns: {debtor_name, amount_ngn, description, due_date, invoice_number}
    """
    prompt = """Extract invoice details from this text. Return JSON only with these exact keys:
{
  "debtor_name": "full name or company name of who owes money",
  "amount_ngn": numeric value in Naira (convert if in USD/GBP),
  "description": "what the invoice is for",
  "due_date": "YYYY-MM-DD format or null if not found",
  "invoice_number": "invoice ref number or null"
}
If amount is in foreign currency, convert to Naira at: 1 USD = 1600 NGN, 1 GBP = 2000 NGN.
Return ONLY the JSON. No preamble."""

    raw = extract_with_gemini(prompt, pdf_text)
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return _json.loads(raw.strip())
    except Exception:
        log.warning("invoice_extraction_parse_failed", raw=raw)
        return {
            "debtor_name": None, "amount_ngn": None,
            "description": None, "due_date": None, "invoice_number": None,
        }


def handle_payment_reply(
    reply_text: str,
    debtor_name: str,
    amount_ngn: float,
    due_date: str,
    product: str = "school_fees",  # "school_fees" | "invoice_chaser" | "rent_collector"
) -> dict:
    """
    Classify an inbound payment reply and generate a context-aware response.
    Uses Claude Haiku — fast and cheap.

    Returns:
        intent:       payment_claim | payment_plan_request | question | dispute | other
        auto_reply:   message to send back to the debtor
        notify_bursar: short summary to forward to the client/bursar
        claimed_paid: bool — True if debtor is claiming they already paid
    """
    client = _get_client()
    product_label = {
        "school_fees": "school fee",
        "invoice_chaser": "invoice",
        "rent_collector": "rent",
    }.get(product, "payment")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                f"You are a professional payment assistant for a Nigerian business. "
                f"A debtor named {debtor_name} replied to a {product_label} reminder. "
                f"Amount owed: ₦{amount_ngn:,.0f}. Due date: {due_date}.\n\n"
                f"Their reply: \"{reply_text}\"\n\n"
                f"Classify the reply and write a short, professional WhatsApp response in Nigerian English. "
                f"Be warm but firm. Never aggressive. Max 3 sentences for the auto_reply.\n\n"
                f"Return JSON only:\n"
                f"{{\n"
                f"  \"intent\": \"payment_claim\" | \"payment_plan_request\" | \"question\" | \"dispute\" | \"other\",\n"
                f"  \"claimed_paid\": true | false,\n"
                f"  \"auto_reply\": \"message to send back to debtor\",\n"
                f"  \"notify_bursar\": \"one-line summary for the client e.g. Bola's parent says they paid Monday\"\n"
                f"}}"
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
        log.warning("handle_payment_reply_parse_failed", raw=raw)
        return {
            "intent": "other",
            "claimed_paid": False,
            "auto_reply": "Thank you for your message. We will follow up shortly.",
            "notify_bursar": f"Reply from {debtor_name}: \"{reply_text[:80]}\"",
        }


def generate_auto_reply_draft(
    original_message: str,
    their_reply: str,
    business_name: str,
    vertical: str,
    intent: str,
    channel: str = "whatsapp",
) -> str:
    """
    Draft a reply to an inbound message based on their intent.
    Used when classify_reply returns interested/question/price_question.
    Returns the draft message text (queued to HITL for human approval before sending).
    """
    intent_instructions = {
        "interested":      (
            "They're interested. Confirm warmly, then ask ONE qualifying question: "
            "either how many [clients/deliveries/employees/deals] they handle per month, "
            "OR what their biggest operational headache is right now. "
            "Keep it conversational — 2 sentences max. End with the qualifying question."
        ),
        "question":        "Answer their question directly. Be helpful and brief. End with a soft next step.",
        "price_question":  "Don't give a full price list. Say pricing depends on their needs and suggest a quick call to understand what they need.",
        "not_now":         "Acknowledge their timing. Keep the door open. Don't push. One sentence max.",
        "referral":        "Thank them for the referral mention. Ask who specifically to contact.",
    }

    instruction = intent_instructions.get(intent, "Respond helpfully and professionally.")

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"You are drafting a reply on behalf of a Lagos business service. "
                f"Vertical: {vertical.replace('_', ' ')}. Channel: {channel}.\n\n"
                f"Your original message to {business_name}:\n\"{original_message}\"\n\n"
                f"Their reply:\n\"{their_reply}\"\n\n"
                f"Intent detected: {intent}. Instruction: {instruction}\n\n"
                f"Write a natural, human-sounding {channel} reply. Max 3 sentences. "
                f"Nigerian English tone — professional but warm. "
                f"Return ONLY the message text. No preamble."
            ),
        }],
    )
    return response.content[0].text.strip()


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
