"""
Try-EYO sandbox endpoint (SPRINT 1 #1).

Public endpoint that lets cold visitors paste a sample customer message and
see EYO draft a reply in real-time. The single biggest landing-page
conversion lever — turns each visit into a live product demo.

Architecture:
  POST /api/v1/try-eyo {vertical, message}
    -> rate-limit by IP (3/min, 20/day)
    -> load per-vertical prompt + the Nigerian context prefix
    -> Anthropic Haiku call (max ~600 tokens output, temp 0.6)
    -> server-side PostHog event `try_eyo_used`
    -> return {reply, vertical, latency_ms}

No DB writes (no client_memory pollution), no Unipile (no real sends).
Sandbox only.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config import get_settings

log = structlog.get_logger()
router = APIRouter(tags=["TryEYO"])

# Verticals exposed in the picker — must match prompt files in agent/prompts/.
SUPPORTED_VERTICALS = {
    "hospitality":           "agent/prompts/hospitality.txt",
    "real_estate":           "agent/prompts/real_estate.txt",
    "clinics":               "agent/prompts/clinics.txt",
    "professional_services": "agent/prompts/professional_services.txt",
    "education":             "agent/prompts/education.txt",
    "small_business":        "agent/prompts/small_business.txt",
}
_PROMPT_CACHE: dict[str, str] = {}

# Rate-limit state (in-memory; fine for single-instance Railway. Promote to
# Redis when we shard).
#   _ip_state[ip] = [timestamps...] within last 24h
_ip_state: dict[str, list[float]] = {}
PER_MIN_CAP = 3
PER_DAY_CAP = 20

_ROOT = Path(__file__).resolve().parent.parent


def _load_prompt(vertical: str) -> str:
    if vertical in _PROMPT_CACHE:
        return _PROMPT_CACHE[vertical]
    path = _ROOT / SUPPORTED_VERTICALS[vertical]
    nigerian_ctx = (_ROOT / "agent/prompts/_nigerian_context.txt")
    body = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = nigerian_ctx.read_text(encoding="utf-8") if nigerian_ctx.exists() else ""
    combined = f"{prefix}\n\n{body}".strip()
    _PROMPT_CACHE[vertical] = combined
    return combined


def _check_rate_limit(ip: str) -> Optional[str]:
    """Returns None if OK, else a human reason string."""
    now = time.time()
    bucket = _ip_state.get(ip, [])
    # Trim to last 24h
    cutoff_day = now - 86400
    bucket = [t for t in bucket if t > cutoff_day]
    cutoff_min = now - 60
    in_last_minute = sum(1 for t in bucket if t > cutoff_min)
    if in_last_minute >= PER_MIN_CAP:
        return f"Too fast — try again in a few seconds. ({PER_MIN_CAP}/min limit)"
    if len(bucket) >= PER_DAY_CAP:
        return f"Daily limit reached ({PER_DAY_CAP}/day). Sign up to remove the cap."
    bucket.append(now)
    _ip_state[ip] = bucket
    return None


# ─── Public types ────────────────────────────────────────────────────────────

class TryEyoRequest(BaseModel):
    vertical: Literal["hospitality", "real_estate", "clinics",
                      "professional_services", "education", "small_business"] = "hospitality"
    message:  str = Field(min_length=4, max_length=600)


@router.post("/api/v1/try-eyo", include_in_schema=False)
async def try_eyo(payload: TryEyoRequest, request: Request):
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(503, "Sandbox temporarily unavailable.")

    # Rate-limit by client IP (X-Forwarded-For first, fallback to client.host)
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))
    block = _check_rate_limit(ip)
    if block:
        raise HTTPException(429, block)

    vertical = payload.vertical
    msg = payload.message.strip()

    system_prompt = _load_prompt(vertical)
    if not system_prompt:
        system_prompt = "You are EYO, an AI WhatsApp operator for a premium Lagos business."

    # Tighten the system prompt for sandbox mode: no real send, no PII collection,
    # one draft reply only, premium-Lagos tone.
    system_prompt += (
        "\n\n--- SANDBOX MODE ---\n"
        "You're being demoed on the public ReachNG landing page. "
        "The visitor pasted a sample customer message. Draft ONE single WhatsApp "
        "reply in the voice of a premium Lagos business owner in this vertical. "
        "Keep it under 80 words. Use Nigerian English. Reference local context "
        "(GTBank/Opay/Paystack, Lagos venues, naira) where natural. Do NOT "
        "include placeholders like [Name] — write as if you've replied this "
        "kind of message hundreds of times. Output only the reply text, nothing else."
    )

    started = time.time()
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Run in a thread so we don't block the event loop on the SDK's sync call.
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            temperature=0.6,
            system=system_prompt,
            messages=[{"role": "user", "content": msg}],
        )
        text = ""
        for block in resp.content or []:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        text = text.strip()
        if not text:
            raise RuntimeError("empty_response")
    except Exception as exc:
        log.warning("try_eyo_failed", error=str(exc), vertical=vertical, ip=ip)
        raise HTTPException(502, "EYO is busy right now — try again in a moment.")

    latency_ms = int((time.time() - started) * 1000)
    log.info("try_eyo_drafted", vertical=vertical, ip=ip,
             input_chars=len(msg), output_chars=len(text), latency_ms=latency_ms)

    # PostHog
    try:
        from services.analytics import track
        track("try_eyo_used",
              distinct_id=f"ip:{ip}",
              vertical=vertical,
              input_chars=len(msg),
              output_chars=len(text),
              latency_ms=latency_ms)
    except Exception:
        pass

    return {
        "reply":      text,
        "vertical":   vertical,
        "latency_ms": latency_ms,
    }
