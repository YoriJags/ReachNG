"""
HITL draft risk scorer (BACKLOG P1 quick-win).

A deterministic, single-pass risk read on every draft as it enters the HITL
queue. Goal: let the operator approve 30 drafts in 90 seconds instead of 6
minutes by surfacing which ones are safe-eyeball vs which deserve careful
reading.

NO LLM CALL — pure rules over the draft + classification + inbound context.
Adds ~0ms to queue_draft latency and ₦0 cost.

Output (persisted on the approval doc under `risk`):
  {
    "confidence":  "high" | "medium" | "low",
    "score":       int 0-100,           # lower = safer
    "tags":        [str],               # flags the operator should know
  }

Confidence thresholds:
  score < 25  → high   (green badge — safe to bulk-approve)
  score < 60  → medium (amber badge — read it)
  score >= 60 → low    (red badge — read carefully, often needs edit)
"""
from __future__ import annotations

import re
from typing import Optional


# ─── Risk weights ─────────────────────────────────────────────────────────────

_MONEY_RE       = re.compile(r"(?:₦|ngn|naira|\$|usd)\s*[\d,]{3,}|[\d,]{4,}\s*(?:₦|ngn|naira|k)", re.I)
_PLACEHOLDER_RE = re.compile(r"\[(?:name|first[\s_-]?name|customer|client|amount|date|time|place|company|business)\]", re.I)
_REFUND_RE      = re.compile(r"\brefund(?:s|ed|ing)?\b", re.I)
_LEGAL_RE       = re.compile(r"\b(?:lawsuit|lawyer|attorney|court|legal action|sue|police|petition|defame|defamation)\b", re.I)
_COMPLAINT_RE   = re.compile(r"\b(?:complain|complaint|disappointed|terrible|awful|worst|unacceptable|fraud|scam|cheat)\b", re.I)
_APOLOGY_RE     = re.compile(r"\b(?:sorry|apologi[sz]e|apolog(?:y|ies))\b", re.I)
_GUARANTEE_RE   = re.compile(r"\b(?:guarantee|promise|definitely|100%|always|never)\b", re.I)
_PRICE_RE       = re.compile(r"\b(?:price|cost|fee|charge|rate|deposit|booking fee)\b", re.I)
_WEDDING_RE     = re.compile(r"\b(?:wedding|engagement|funeral|burial|chieftaincy|christening)\b", re.I)

# Verticals where "premium tone" matters more — extra weight on long replies + apology overuse
_PREMIUM_VERTICALS = {"real_estate", "legal", "clinics", "professional_services"}


def score_draft(
    *,
    message: str,
    classification: Optional[dict] = None,
    inbound_context: Optional[str] = None,
    vertical: Optional[str] = None,
    escalated: bool = False,
) -> dict:
    """
    Return {confidence, score, tags} for a draft. Deterministic, no I/O.
    """
    msg  = message or ""
    inb  = inbound_context or ""
    cls  = classification or {}
    tags: list[str] = []
    score = 0

    # ── Hard-block signals ──────────────────────────────────────────────────
    if escalated or cls.get("escalate"):
        score += 50
        tags.append("escalated")

    if cls.get("urgency") == "on_fire" and cls.get("sentiment") == "angry":
        score += 40
        tags.append("angry_on_fire")
    elif cls.get("sentiment") == "angry":
        score += 25
        tags.append("angry")
    elif cls.get("urgency") == "on_fire":
        score += 15
        tags.append("on_fire")

    if cls.get("stage") == "complaint":
        score += 30
        tags.append("complaint_stage")

    # ── Content-of-draft signals ────────────────────────────────────────────
    if _PLACEHOLDER_RE.search(msg):
        score += 60
        tags.append("placeholder_leak")  # the drafter forgot to fill in a slot — always fix before sending

    if _LEGAL_RE.search(msg) or _LEGAL_RE.search(inb):
        score += 35
        tags.append("legal_mentioned")

    if _COMPLAINT_RE.search(inb):
        score += 20
        tags.append("inbound_complaint")

    if _REFUND_RE.search(msg) or _REFUND_RE.search(inb):
        score += 25
        tags.append("refund_topic")

    if _WEDDING_RE.search(inb):
        score += 15
        tags.append("high_stakes_event")

    if _GUARANTEE_RE.search(msg):
        score += 15
        tags.append("overpromise")

    if _MONEY_RE.search(msg):
        score += 10
        tags.append("money_quoted")
    elif _PRICE_RE.search(msg):
        score += 5
        tags.append("price_topic")

    # ── Length / structure signals ──────────────────────────────────────────
    n = len(msg.strip())
    if n > 800:
        score += 15
        tags.append("very_long")
    elif n > 500:
        score += 8
        tags.append("long")
    elif n < 20:
        score += 25
        tags.append("very_short")  # almost certainly under-explained

    # Apology in premium vertical = often a tone risk (over-apologising)
    if vertical in _PREMIUM_VERTICALS:
        apologies = len(_APOLOGY_RE.findall(msg))
        if apologies >= 2:
            score += 10
            tags.append("over_apologetic")

    # ── No inbound context = first-touch / cold; less risky but worth noting
    if not inb.strip():
        tags.append("no_inbound_context")

    # Clamp
    score = max(0, min(100, score))

    if score < 25:
        confidence = "high"
    elif score < 60:
        confidence = "medium"
    else:
        confidence = "low"

    return {"confidence": confidence, "score": score, "tags": tags}
