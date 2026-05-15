"""
Inbound Classifier — emotional / stage / urgency read before drafting.

The agent gets visibly smarter the moment it stops drafting every reply with
the same default tone. This module classifies every inbound message on three
axes via a single Haiku 4.5 call (~200-400ms, ~₦2 per call) and feeds the
result back into the drafter as a TONE GUIDANCE block.

The three axes
--------------
  sentiment ∈ {happy, neutral, frustrated, angry}
  stage     ∈ {first_touch, qualifying, negotiating, closing, post_sale, complaint}
  urgency   ∈ {idle, interested, hot, on_fire}

Why each axis matters
---------------------
  sentiment → controls warmth: angry gets apology framing, happy gets celebration
  stage     → controls density: first_touch is friendly + scene-setting,
              negotiating is concrete, closing is brisk + confident, complaint
              is acknowledgement-first-then-action
  urgency   → controls pace: on_fire surfaces at top of queue + propose deposit
              instantly; idle gets a relaxed nudge

Escalation
----------
Any of these auto-flags the draft for owner attention (banner + top-of-queue):
  • sentiment == angry
  • stage     == complaint
  • urgency   == on_fire AND confidence > 0.7
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional

import structlog

from config import get_settings

log = structlog.get_logger()


# ─── Vocab ────────────────────────────────────────────────────────────────────

SENTIMENTS = ("happy", "neutral", "frustrated", "angry")
STAGES = ("first_touch", "qualifying", "negotiating", "closing", "post_sale", "complaint")
URGENCIES = ("idle", "interested", "hot", "on_fire")


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class InboundClassification:
    sentiment:     str
    stage:         str
    urgency:       str
    confidence:    float           # 0-1, how confident the classifier is
    escalate:      bool            # true if angry / complaint / on_fire+confident
    tone_guidance: str             # the drafter-facing instruction block
    reasoning:     Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Defaults / fallback ──────────────────────────────────────────────────────

def _safe_default() -> InboundClassification:
    return InboundClassification(
        sentiment="neutral",
        stage="qualifying",
        urgency="interested",
        confidence=0.3,
        escalate=False,
        tone_guidance="Default professional Lagos-SME tone — warm, specific, no fluff.",
        reasoning="fallback (classifier unavailable or parse failed)",
    )


# ─── System prompt for Haiku ─────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """You are an inbound-message classifier for a Nigerian SME's
WhatsApp business line. You read ONE inbound message (and optionally recent
thread context) and return a strict JSON object describing it on three axes.

AXES — return EXACTLY these vocabularies, lowercase:

  sentiment ∈ ["happy", "neutral", "frustrated", "angry"]
  stage     ∈ ["first_touch", "qualifying", "negotiating", "closing", "post_sale", "complaint"]
  urgency   ∈ ["idle", "interested", "hot", "on_fire"]

GUIDANCE
- "happy" needs explicit positive cue (thanks, smileys, excitement).
- "frustrated" = annoyed but reasonable. "angry" = hostile, complaining, threatening, capslock.
- "first_touch" = brand new, no prior context. "qualifying" = asking about offer/pricing.
  "negotiating" = pushing on price/terms. "closing" = ready to pay/book.
  "post_sale" = already a customer asking about delivery/support.
  "complaint" = explicit grievance about something already received/promised.
- "idle" = lukewarm enquiry. "interested" = engaged + replying. "hot" = clear intent
  to move soon ("can I book today?"). "on_fire" = explicit urgency ("need it before
  Saturday", "my flight is tomorrow"), or high-value + ready.

Also return:
  confidence: float 0-1 — how confident you are in the read
  tone_guidance: 1-2 sentence drafting instruction tailored to this read, e.g.
    "Acknowledge the frustration first. Apologise specifically for the late reply.
     Then offer a concrete remedy. Keep it human, no corporate language."
  reasoning: one short sentence explaining the read.

OUTPUT FORMAT — JSON only, no markdown, no preamble:
{"sentiment": "...", "stage": "...", "urgency": "...", "confidence": 0.8,
 "tone_guidance": "...", "reasoning": "..."}
"""


# ─── Tone guidance fallback (deterministic) ───────────────────────────────────

def _deterministic_tone_guidance(sentiment: str, stage: str, urgency: str) -> str:
    parts = []
    if sentiment == "angry":
        parts.append("Open with explicit acknowledgement and apology — name what went wrong before anything else.")
    elif sentiment == "frustrated":
        parts.append("Lead with empathy. Acknowledge their frustration in one short sentence before answering.")
    elif sentiment == "happy":
        parts.append("Match their energy — warm and slightly upbeat is fine here.")

    if stage == "complaint":
        parts.append("This is a complaint, not a sale. Focus on resolution, not pitching.")
    elif stage == "negotiating":
        parts.append("Be concrete on numbers. Offer one specific accommodation if appropriate, hold the line on the rest.")
    elif stage == "closing":
        parts.append("They're ready. Be brisk. Send the Paystack/payment link in this same message.")
    elif stage == "first_touch":
        parts.append("Set the scene briefly, then ask one qualifying question to move things forward.")
    elif stage == "post_sale":
        parts.append("They're already a customer. Skip the sales tone. Be quick and useful.")

    if urgency == "on_fire":
        parts.append("Time-sensitive. Propose the next step (booking/payment) in this reply, don't wait.")
    elif urgency == "hot":
        parts.append("Don't dawdle. Move toward commitment in this reply.")
    elif urgency == "idle":
        parts.append("No rush — a relaxed, friendly tone is fine.")

    if not parts:
        parts.append("Default professional Lagos-SME tone — warm, specific, no fluff.")
    return " ".join(parts)


# ─── Public ──────────────────────────────────────────────────────────────────

def classify_inbound(
    inbound_text: str,
    *,
    vertical: Optional[str] = None,
    recent_context: Optional[str] = None,
    contact_name: Optional[str] = None,
) -> InboundClassification:
    """Classify a single inbound. Returns a safe default on any error — never raises."""
    if not (inbound_text or "").strip():
        return _safe_default()

    settings = get_settings()
    if not settings.anthropic_api_key:
        log.info("classifier_skipped_no_key")
        return _safe_default()

    user_block: list[str] = []
    if contact_name:
        user_block.append(f"Contact name: {contact_name}")
    if vertical:
        user_block.append(f"Business vertical: {vertical}")
    if recent_context:
        user_block.append(f"Recent thread context:\n{recent_context[:800]}")
    user_block.append(f"Inbound message:\n{inbound_text[:1500]}")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(user_block)}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        log.warning("classifier_call_failed", error=str(e))
        return _safe_default()

    # Tolerant JSON parse
    if raw.startswith("```"):
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        else:
            return _safe_default()
    try:
        data = json.loads(raw)
    except Exception:
        log.warning("classifier_json_parse_failed", raw_head=raw[:120])
        return _safe_default()

    sentiment = (data.get("sentiment") or "neutral").strip().lower()
    stage = (data.get("stage") or "qualifying").strip().lower()
    urgency = (data.get("urgency") or "interested").strip().lower()
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"
    if stage not in STAGES:
        stage = "qualifying"
    if urgency not in URGENCIES:
        urgency = "interested"

    try:
        confidence = float(data.get("confidence", 0.6) or 0.6)
    except Exception:
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    tone_guidance = (data.get("tone_guidance") or "").strip()
    if not tone_guidance:
        tone_guidance = _deterministic_tone_guidance(sentiment, stage, urgency)

    escalate = (
        sentiment == "angry"
        or stage == "complaint"
        or (urgency == "on_fire" and confidence >= 0.7)
    )

    return InboundClassification(
        sentiment=sentiment,
        stage=stage,
        urgency=urgency,
        confidence=round(confidence, 3),
        escalate=escalate,
        tone_guidance=tone_guidance,
        reasoning=(data.get("reasoning") or "").strip() or None,
    )


# ─── Drafter-facing helper ────────────────────────────────────────────────────

def format_tone_block(c: InboundClassification) -> str:
    """Wrap the classification as a TONE GUIDANCE block for prompt injection."""
    parts = [
        "TONE GUIDANCE for this specific message (must honour):",
        f"  sentiment: {c.sentiment}    stage: {c.stage}    urgency: {c.urgency}",
        f"  → {c.tone_guidance}",
    ]
    if c.escalate:
        parts.append("  ⚠ This message warrants owner attention. Match the gravity in your draft.")
    return "\n".join(parts)


# ─── Badge helper for HITL UI ─────────────────────────────────────────────────

_EMOJI = {
    "happy":       "😊",
    "neutral":     "💬",
    "frustrated":  "😤",
    "angry":       "🔥",
    "first_touch": "👋",
    "qualifying":  "🔎",
    "negotiating": "🤝",
    "closing":     "💸",
    "post_sale":   "📦",
    "complaint":   "⚠️",
    "idle":        "🌿",
    "interested":  "📈",
    "hot":         "🔥",
    "on_fire":     "🚨",
}


def badge_html(c: InboundClassification) -> str:
    """Inline HTML badge string for HITL queue rendering."""
    sent_e = _EMOJI.get(c.sentiment, "")
    stage_e = _EMOJI.get(c.stage, "")
    urg_e = _EMOJI.get(c.urgency, "")
    klass = "esc" if c.escalate else "normal"
    return (
        f'<span class="emo-badge emo-{klass}" data-conf="{c.confidence}">'
        f'{sent_e} {c.sentiment}'
        f' &middot; {stage_e} {c.stage.replace("_", " ")}'
        f' &middot; {urg_e} {c.urgency.replace("_", " ")}'
        f'</span>'
    )
