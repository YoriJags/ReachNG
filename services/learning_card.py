"""
Instant Learning Card (#3).

The moment an owner edits a draft before approving, EYO should say —
right there — what it just learned:

  "EYO learned: don't open with 'Dear'; use 'Hi boss'."

The weekly Outcome Loop (services/outcome_learning.py) already distils edits
into a durable prompt addendum. This is the *instant* feel-alive surface: one
cheap Haiku call diffing original → edited, returning a single lesson line.

Cheap by design: skipped when the edit is trivial or no API key is set.
Lessons are also stored (best-effort) in `learning_cards` for an activity feed.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from config import get_settings
from database import get_db

log = structlog.get_logger()

_SYSTEM = (
    "You are EYO, an AI sales assistant for a Lagos business. The owner just "
    "edited your draft reply before sending. Compare YOUR draft to the OWNER'S "
    "final version and state, in ONE short imperative line (max 12 words), the "
    "single most useful voice/style/policy lesson to remember next time. "
    "Write it as the lesson itself, no preamble, no quotes. "
    "If the change is only a typo, punctuation, or trivial wording with no "
    "real lesson, output exactly: NONE"
)


def _trivial(a: str, b: str) -> bool:
    a2 = " ".join((a or "").lower().split())
    b2 = " ".join((b or "").lower().split())
    if a2 == b2:
        return True
    # Tiny edits (a few chars) rarely carry a lesson worth surfacing.
    return abs(len(a2) - len(b2)) <= 3 and a2[:20] == b2[:20]


async def instant_insight(original: str, edited: str, vertical: Optional[str] = None) -> Optional[str]:
    """One-line 'EYO learned: …' lesson, or None when there's nothing to learn."""
    if not original or not edited or _trivial(original, edited):
        return None
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        prompt = (
            f"Vertical: {vertical or 'general'}\n\n"
            f"MY DRAFT:\n{original.strip()[:1200]}\n\n"
            f"OWNER'S FINAL:\n{edited.strip()[:1200]}"
        )
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=40,
            temperature=0.0,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (resp.content or [])
            if getattr(b, "type", "") == "text"
        ).strip().strip('"').strip()
        if not text or text.upper() == "NONE" or len(text) > 120:
            return None
        return text
    except Exception as e:
        log.warning("instant_insight_failed", error=str(e))
        return None


def record_card(client_name: str, lesson: str, contact_name: str = "") -> None:
    """Best-effort persist for the 'EYO is learning' feed."""
    try:
        get_db()["learning_cards"].insert_one({
            "client_name":  client_name,
            "lesson":       lesson[:200],
            "contact_name": contact_name[:80],
            "created_at":   datetime.now(timezone.utc),
        })
    except Exception:
        pass
