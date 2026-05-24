"""
Tone guardrails — single source of truth for never-say enforcement.

Applied at the queue_draft boundary in tools/hitl.py so EVERY outbound draft
(real or sandbox) gets the same scrub. Cheap, idempotent, runs in-process.

Why post-scrub instead of relying on the system prompt alone:
- Haiku occasionally ignores the never-say rule under high-creativity prompts.
- A single regex pass at the boundary is bulletproof. If the model gets it
  right, the regex is a no-op. If it slips, the customer never sees the slip.
"""
from __future__ import annotations

import re

# Casual endearments banned from any customer-facing draft. These are PREMIUM
# Lagos/Abuja businesses replying to PAYING customers — never "babe", "love"
# or the like, even if Haiku thinks it's being warm.
ENDEARMENTS = (
    "babe", "bae", "love", "lovey", "dear", "darling", "darl",
    "sweetie", "sweetheart", "sweet", "honey", "hun",
    "boo", "fam", "bro", "sis", "sister", "brother",
    "my dear",
)

# Match endearment preceded by whitespace, as a whole word.
# Removes the leading space too so 'Hey babe!' -> 'Hey!' cleanly.
_ENDEAR_RE = re.compile(
    r"(?:\s+)(?:" + "|".join(re.escape(w) for w in ENDEARMENTS) + r")\b",
    flags=re.IGNORECASE,
)


def scrub_endearments(text: str) -> str:
    """Strip casual endearments from a customer-facing draft.

    Examples:
        'Hey babe! Congrats!'        -> 'Hey! Congrats!'
        'Thanks dear, your booking…' -> 'Thanks, your booking…'
        'Hello my dear, welcome.'    -> 'Hello, welcome.'
        'Hi Funke! Yes.'             -> 'Hi Funke! Yes.'   (real names preserved)

    Idempotent — running twice is a no-op.
    """
    if not text:
        return text
    out = _ENDEAR_RE.sub("", text)
    # Heal artefacts: 'Hey !' -> 'Hey!', 'Hello , what' -> 'Hello, what'.
    out = re.sub(r"\s+([,!\?\.])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()
