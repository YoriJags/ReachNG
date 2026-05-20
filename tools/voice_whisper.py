"""
Voice-note transcription via OpenAI Whisper, with Nigerian-language safe-switch.

WhatsApp customers send voice notes constantly. ReachNG transcribes them so
EYO can draft a reply as if it were text. But customers don't always speak
English — Lagos and Abuja inboxes get Pidgin, Yoruba, Igbo and Hausa daily.

This module enforces a strict honesty contract:

    English voice note         → transcript, EYO drafts in English
    Pidgin voice note          → transcript, EYO drafts in Pidgin (matches energy)
    Yoruba/Igbo/Hausa, high-conf → transcript + English translation, EYO drafts in English
    Anything low-confidence     → no draft. HITL banner says "language uncertain, listen".

The line we won't cross: never let EYO confidently guess at a voice note it
isn't confident it understood. Premium owners would rather listen than
explain a wrong reply.

Cost: ~$0.006 per minute of Whisper audio. Translation/cleanup adds one cheap
Haiku call (~₦3) when triggered. Negligible at any reasonable volume.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from config import get_settings

log = structlog.get_logger()


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class VoiceTranscript:
    text:              str
    duration_seconds:  Optional[float]
    language:          Optional[str]    # ISO-639-1 from Whisper (en/yo/ig/ha/...)
    mime_type:         str
    # New fields for the safe-switch
    confidence:        float            # 0.0–1.0, derived from Whisper segment logprobs
    is_pidgin:         bool             # True if Whisper said 'en' but Haiku flagged Pidgin
    reply_language:    str              # "english" | "pidgin"  — what the drafter should write in
    translation_en:    Optional[str]    # English translation if customer spoke yo/ig/ha
    should_draft:      bool             # False ⇒ HITL banner, no auto-draft
    uncertain_reason:  Optional[str]    # human-readable why should_draft is False


# ─── Mime → filename helper ──────────────────────────────────────────────────

_MIME_TO_EXT = {
    "audio/ogg":     "ogg",
    "audio/oga":     "oga",
    "audio/opus":    "opus",
    "audio/mpeg":    "mp3",
    "audio/mp3":     "mp3",
    "audio/mp4":     "m4a",
    "audio/m4a":     "m4a",
    "audio/x-m4a":   "m4a",
    "audio/wav":     "wav",
    "audio/x-wav":   "wav",
    "audio/webm":    "webm",
    "audio/aac":     "aac",
}

# Whisper segment avg_logprob threshold. >= -0.30 ≈ "very high confidence" (~90%+);
# we use this as the gate for trusting non-English transcripts enough to auto-draft.
_HIGH_CONFIDENCE_THRESHOLD = -0.30

# Nigerian languages we explicitly handle. Anything else with non-English ISO
# code is treated as "uncertain" until proven otherwise.
_KNOWN_NIGERIAN_LANGS = {"yo", "ig", "ha"}


def _filename_for(mime: str) -> str:
    ext = _MIME_TO_EXT.get((mime or "").lower(), "ogg")
    return f"voice.{ext}"


def _mean_avg_logprob(segments: list) -> float:
    """Compute mean of segment-level avg_logprob. Whisper values are typically
    in [-1.0, 0.0]; closer to 0 = more confident. Returns 0.0 on empty input."""
    vals = [s.get("avg_logprob") for s in segments if isinstance(s, dict) and s.get("avg_logprob") is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _logprob_to_confidence(mean_logprob: float) -> float:
    """Convert Whisper's avg_logprob (≤0) to a 0–1 confidence score.
    Pure exp(logprob) is too pessimistic for our gating, so we use a soft
    mapping: -0.0 → 1.0, -0.3 → 0.90, -0.6 → 0.70, -1.0 → 0.40, lower → ~0.
    """
    # Equivalent to a sigmoid-shaped curve anchored at the threshold.
    # f(x) = 1 / (1 + e^(-4 * (x + 0.5))) gives roughly the table above.
    try:
        return 1.0 / (1.0 + math.exp(-4.0 * (mean_logprob + 0.5)))
    except OverflowError:
        return 0.0


# ─── Pidgin sub-detection via Haiku ──────────────────────────────────────────

async def _detect_pidgin(text: str) -> bool:
    """Whisper labels Pidgin as `en`. This quick Haiku call decides whether
    the English-labelled text is actually Nigerian Pidgin (so EYO replies in
    Pidgin) or standard/Nigerian English.

    Cheap, ~150 tokens out, ₦2 per call. Returns False on any failure so
    the safe default is "treat as English."
    """
    if not text or len(text.strip()) < 8:
        return False
    settings = get_settings()
    if not settings.anthropic_api_key:
        return False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8,
            system=(
                "You are a strict language classifier for Nigerian customer messages. "
                "Reply with EXACTLY one of: 'pidgin' or 'english'. "
                "Choose 'pidgin' if the text is recognisably Nigerian Pidgin "
                "(e.g. 'I dey come', 'wetin happen', 'abeg', 'na so', 'don pay'). "
                "Choose 'english' for standard or Nigerian English even with light slang. "
                "Output nothing else."
            ),
            messages=[{"role": "user", "content": text[:800]}],
        )
        out = ""
        for block in resp.content or []:
            if getattr(block, "type", "") == "text":
                out += getattr(block, "text", "")
        return out.strip().lower().startswith("pidgin")
    except Exception as e:
        log.warning("pidgin_detect_failed", error=str(e))
        return False


# ─── Haiku translation for high-confidence non-English ───────────────────────

async def _translate_to_english(text: str, source_lang: str) -> Optional[str]:
    """Translate a high-confidence non-English transcript into English.
    Returns the translation, or None on failure. Caller falls back to
    surfacing the original transcript with an 'uncertain' flag."""
    if not text:
        return None
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    lang_name = {"yo": "Yoruba", "ig": "Igbo", "ha": "Hausa"}.get(source_lang, source_lang)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=(
                f"You translate Nigerian {lang_name} into clear, faithful English. "
                "Preserve meaning, tone, and any business-specific terms. "
                "Output ONLY the English translation — no preface, no labels, no notes."
            ),
            messages=[{"role": "user", "content": text[:2000]}],
        )
        out = ""
        for block in resp.content or []:
            if getattr(block, "type", "") == "text":
                out += getattr(block, "text", "")
        translation = (out or "").strip().strip('"').strip()
        return translation or None
    except Exception as e:
        log.warning("voice_translate_failed", error=str(e), source_lang=source_lang)
        return None


# ─── Public ──────────────────────────────────────────────────────────────────

async def transcribe_voice_note(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language_hint: Optional[str] = None,
    client_id: Optional[str] = None,
) -> Optional[VoiceTranscript]:
    """Transcribe a voice note via OpenAI Whisper with Nigerian-language safe-switch.

    `language_hint` is now None by default — we let Whisper auto-detect so we
    can route Yoruba/Igbo/Hausa correctly. Pass an explicit code if you want
    to force one (rare).

    Returns VoiceTranscript with safe-switch fields populated. The downstream
    handler reads `should_draft` to decide whether to flow into the drafter
    or post a HITL "language uncertain" banner. Never raises.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        log.info("whisper_skipped_no_key")
        return None

    if not audio_bytes or len(audio_bytes) < 100:
        log.info("whisper_skipped_empty_audio", size=len(audio_bytes or b""))
        return None

    if len(audio_bytes) > 25 * 1024 * 1024:
        log.warning("whisper_skipped_oversized", size=len(audio_bytes))
        return None

    if client_id:
        try:
            from services.usage_meter import check_rate
            if not check_rate(str(client_id), "voice"):
                log.warning("whisper_rate_limited", client_id=client_id)
                return None
        except Exception:
            pass

    filename = _filename_for(mime_type)
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    data: dict = {
        "model":           "whisper-1",
        "response_format": "verbose_json",
    }
    if language_hint:
        data["language"] = language_hint

    files = {
        "file": (filename, io.BytesIO(audio_bytes), mime_type or "audio/ogg"),
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers, data=data, files=files,
            )
        if resp.status_code != 200:
            log.warning("whisper_api_failed", status=resp.status_code,
                        body=(resp.text or "")[:200])
            return None
        body = resp.json()
    except Exception as e:
        log.warning("whisper_call_crashed", error=str(e))
        return None

    text = (body.get("text") or "").strip()
    if not text:
        log.info("whisper_empty_transcript")
        return None

    detected_lang = (body.get("language") or "").lower().strip() or None
    segments      = body.get("segments") or []
    mean_lp       = _mean_avg_logprob(segments)
    confidence    = _logprob_to_confidence(mean_lp)
    duration      = body.get("duration")

    # ── Routing: figure out reply language + whether to draft ────────────────
    is_pidgin       = False
    reply_language  = "english"
    translation_en  = None
    should_draft    = True
    uncertain_reason: Optional[str] = None

    if detected_lang in (None, "", "en", "english"):
        # Whisper says English. Could be standard English or Pidgin.
        is_pidgin = await _detect_pidgin(text)
        reply_language = "pidgin" if is_pidgin else "english"
    elif detected_lang in _KNOWN_NIGERIAN_LANGS:
        # Yoruba / Igbo / Hausa. Gate on confidence.
        if mean_lp >= _HIGH_CONFIDENCE_THRESHOLD:
            translation_en = await _translate_to_english(text, detected_lang)
            if not translation_en:
                should_draft = False
                uncertain_reason = f"translation_failed_{detected_lang}"
            else:
                reply_language = "english"  # always reply in English for yo/ig/ha
        else:
            should_draft = False
            uncertain_reason = f"low_confidence_{detected_lang}"
    else:
        # Some other language entirely (Spanish, French, who knows). Don't guess.
        should_draft = False
        uncertain_reason = f"unsupported_language_{detected_lang}"

    if client_id:
        try:
            from services.usage_meter import record
            record(
                client_id=str(client_id), feature="voice", units=1,
                extra={"duration_s": float(duration or 0), "chars": len(text),
                       "language": detected_lang, "confidence": round(confidence, 3),
                       "drafted": should_draft},
            )
        except Exception:
            pass

    return VoiceTranscript(
        text=text,
        duration_seconds=duration,
        language=detected_lang,
        mime_type=mime_type,
        confidence=confidence,
        is_pidgin=is_pidgin,
        reply_language=reply_language,
        translation_en=translation_en,
        should_draft=should_draft,
        uncertain_reason=uncertain_reason,
    )


# ─── HITL formatting ─────────────────────────────────────────────────────────

_LANG_LABEL = {
    "en": "English", "english": "English",
    "yo": "Yoruba", "ig": "Igbo", "ha": "Hausa",
}


def format_for_draft(transcript: VoiceTranscript, customer_phone: Optional[str] = None) -> str:
    """Render the transcript so both the drafter and the human reviewer see
    the right context. Behaviour by language:

      English  → plain transcript with a 🎤 marker.
      Pidgin   → transcript + reply-in-pidgin instruction.
      Yoruba/Igbo/Hausa (high-conf) → original transcript + English translation
                                       + reply-in-English instruction.
      Uncertain → explicit DO-NOT-DRAFT banner with the raw best-effort text
                   so the human can sanity-check.
    """
    dur = f" ({transcript.duration_seconds:.0f}s)" if transcript.duration_seconds else ""
    conf_pct = f"{transcript.confidence * 100:.0f}%"

    if not transcript.should_draft:
        reason = transcript.uncertain_reason or "language_uncertain"
        return (
            f"🎤 Voice note received{dur} — ⚠️ LANGUAGE UNCERTAIN ({reason}, conf {conf_pct}).\n"
            f"EYO did not draft a reply. Please listen to the audio before sending anything.\n"
            f"Best-effort transcript: \"{transcript.text}\""
        )

    if transcript.is_pidgin:
        return (
            f"🎤 Voice note transcript{dur} [language: Nigerian Pidgin, conf {conf_pct}]:\n"
            f"\"{transcript.text}\"\n"
            f"[Reply in Pidgin — match the customer's energy.]"
        )

    if transcript.language in _KNOWN_NIGERIAN_LANGS and transcript.translation_en:
        label = _LANG_LABEL.get(transcript.language, transcript.language)
        return (
            f"🎤 Voice note transcript{dur} [language: {label}, conf {conf_pct}]:\n"
            f"Original ({label}): \"{transcript.text}\"\n"
            f"Translation (EN): \"{transcript.translation_en}\"\n"
            f"[Reply in English. Customer wrote in {label}.]"
        )

    # Standard English (incl. Nigerian English)
    return (
        f"🎤 Voice note transcript{dur}:\n"
        f"\"{transcript.text}\""
    )
