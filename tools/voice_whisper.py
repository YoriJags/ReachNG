"""
Voice-note transcription via OpenAI Whisper.

WhatsApp customers send voice notes constantly — especially in hospitality,
real estate, and beauty. A 45-second voice note is faster for them than typing
but it kills owner throughput (12 voice notes at 9pm = nobody listens).

This module takes the audio bytes ReachNG already downloads via
`tools/inbound_media.py` and runs them through OpenAI's Whisper API, returning
a clean transcript that flows into the existing drafter as if it were text.

Cost: ~$0.006 per minute of audio (≈₦10 per minute at today's FX). A typical
voice note is 20-60s so call it ₦5-10 per transcription. Negligible.

Latency: ~2-4 seconds for a 60s clip.

Failure mode: if OPENAI_API_KEY missing or the API errors, returns None and
the inbound is handled as if no media was present (caller logs + moves on).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from config import get_settings

log = structlog.get_logger()


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class VoiceTranscript:
    text:             str
    duration_seconds: Optional[float]   # if Whisper returned a duration
    language:         Optional[str]     # ISO-639-1 if detected
    mime_type:        str


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


def _filename_for(mime: str) -> str:
    ext = _MIME_TO_EXT.get((mime or "").lower(), "ogg")
    return f"voice.{ext}"


# ─── Public ──────────────────────────────────────────────────────────────────

async def transcribe_voice_note(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language_hint: Optional[str] = "en",
    client_id: Optional[str] = None,   # T0.2.5 — metering scope
) -> Optional[VoiceTranscript]:
    """Transcribe a voice-note via OpenAI Whisper.

    `language_hint` defaults to 'en'. Nigerian customers code-switch between
    English and Pidgin (and occasionally Yoruba/Hausa/Igbo). Whisper handles
    code-mixed English-Pidgin well; passing 'en' improves accuracy on common
    Nigerian terms. Pass None to let Whisper auto-detect.

    Returns VoiceTranscript on success, None if OPENAI_API_KEY is missing or
    the API call fails. Never raises — caller handles None.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        log.info("whisper_skipped_no_key")
        return None

    if not audio_bytes or len(audio_bytes) < 100:
        log.info("whisper_skipped_empty_audio", size=len(audio_bytes or b""))
        return None

    # 25MB OpenAI limit. WhatsApp voice notes are tiny (a 5-min clip is ~500KB)
    # so we'd only hit this with deliberately large attached audio.
    if len(audio_bytes) > 25 * 1024 * 1024:
        log.warning("whisper_skipped_oversized", size=len(audio_bytes))
        return None

    # T0.2.5 — anti-runaway rate-limit gate (20 voice/min per client)
    if client_id:
        try:
            from services.usage_meter import check_rate
            if not check_rate(str(client_id), "voice"):
                log.warning("whisper_rate_limited", client_id=client_id)
                return None
        except Exception:
            pass   # never let metering break the actual call

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
                headers=headers,
                data=data,
                files=files,
            )
        if resp.status_code != 200:
            log.warning(
                "whisper_api_failed",
                status=resp.status_code,
                body=(resp.text or "")[:200],
            )
            return None
        body = resp.json()
    except Exception as e:
        log.warning("whisper_call_crashed", error=str(e))
        return None

    text = (body.get("text") or "").strip()
    if not text:
        log.info("whisper_empty_transcript")
        return None

    # T0.2.5 — record successful usage event (best-effort, never blocks return)
    if client_id:
        try:
            from services.usage_meter import record
            dur = body.get("duration") or 0
            record(
                client_id=str(client_id),
                feature="voice",
                units=1,
                extra={"duration_s": float(dur), "chars": len(text)},
            )
        except Exception:
            pass

    return VoiceTranscript(
        text=text,
        duration_seconds=body.get("duration"),
        language=body.get("language"),
        mime_type=mime_type,
    )


def format_for_draft(transcript: VoiceTranscript, customer_phone: Optional[str] = None) -> str:
    """Wrap the raw transcript so the drafter (and the operator in HITL) knows
    this text came from a voice note, not a typed message.

    The drafter treats the transcript as the inbound text; the wrapper helps
    operators auditing the queue understand context.
    """
    dur = ""
    if transcript.duration_seconds:
        dur = f" ({transcript.duration_seconds:.0f}s)"
    lang_tag = ""
    if transcript.language and transcript.language.lower() not in {"en", "english"}:
        lang_tag = f" [language: {transcript.language}]"
    return (
        f"🎤 Voice note transcript{dur}{lang_tag}:\n"
        f"\"{transcript.text}\""
    )
