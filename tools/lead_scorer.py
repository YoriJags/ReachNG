"""
Lead Quality Scorer — produces a Hot / Warm / Cold verdict + reasons for any contact.

Extends the existing tools/scoring.py::score_contact() with richer signals
(enrichment payload, decision-maker presence, email quality, recency) and
adds a human-readable verdict + reason list so the operator + drafter can
decide who's worth API spend.

Why we score
------------
Every drafter call costs ~₦4. Every Apify/Apollo enrichment call costs ~₦40.
A bad lead (no website, 2.8 Maps rating, no decision-maker) burns those
credits with near-zero close probability. The scorer's job is to either:
  • Park cold leads at the bottom of the queue (no spend on them)
  • Or filter them out entirely from prospecting campaigns

Output shape
------------
    {
        "score":   78,
        "verdict": "hot",            # "hot" | "warm" | "cold"
        "reasons": ["4.6 Maps rating", "decision-maker on file", "website live"],
        "negatives": ["no email address"]
    }

Verdict thresholds (tunable below):
    hot   >= 70
    warm  >= 40
    cold  <  40

Deterministic — NO LLM calls. Single-pass over the contact doc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from tools.scoring import score_contact, HIGH_VALUE_CATEGORIES


# ─── Verdict thresholds ──────────────────────────────────────────────────────

HOT_THRESHOLD = 70
WARM_THRESHOLD = 40


# ─── Result type ─────────────────────────────────────────────────────────────

@dataclass
class LeadScore:
    score:     int                                  # 0-120 (richer than the base 0-100)
    verdict:   str                                  # "hot" | "warm" | "cold"
    reasons:   list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Signal extractors ───────────────────────────────────────────────────────

_GENERIC_EMAIL_PREFIXES = {"info", "hello", "contact", "admin", "support",
                            "sales", "office", "mail", "enquiries", "enquiry"}


def _email_quality_bonus(email: Optional[str]) -> tuple[int, str]:
    """Direct/personal email = +10. Generic info@ = +3."""
    if not email or "@" not in email:
        return 0, ""
    local = email.split("@", 1)[0].lower().strip()
    if local in _GENERIC_EMAIL_PREFIXES:
        return 3, "email on file (generic info@)"
    # Looks like a person ("firstname.lastname@", or "firstname@")
    return 10, f"direct email on file ({email})"


def _decision_maker_bonus(contact: dict, enrichment: Optional[dict]) -> tuple[int, str]:
    """Decision-maker name present = +15."""
    name = contact.get("contact_name") or contact.get("decision_maker")
    if not name and enrichment:
        team = enrichment.get("team_names") or []
        if team:
            name = team[0]
    if name:
        title = contact.get("contact_title") or ""
        descr = f"decision-maker on file: {name}" + (f" ({title})" if title else "")
        return 15, descr
    return 0, ""


def _recency_bonus(contact: dict) -> tuple[int, str]:
    """Recent enrichment / last-updated timestamp = +5."""
    last = contact.get("enriched_at") or contact.get("updated_at")
    if not last:
        return 0, ""
    try:
        if isinstance(last, str):
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return 0, ""
    age_days = (datetime.now(timezone.utc) - last).days
    if age_days < 30:
        return 5, "fresh data (<30d)"
    if age_days > 365:
        return -5, "data over 1 year stale"
    return 0, ""


def _signal_bonus(contact: dict) -> tuple[int, list[str]]:
    """Social signal triggers from signal_listener (IG/Twitter intent posts)."""
    sig = contact.get("signal_data") or {}
    bonus = 0
    reasons: list[str] = []
    if sig.get("intent_post"):
        bonus += 10
        reasons.append(f"intent signal on {sig.get('platform', 'social')}")
    if sig.get("pain_keywords"):
        bonus += 5
        reasons.append("pain-keyword match on social")
    return bonus, reasons


def _activity_signals(contact: dict) -> tuple[int, list[str]]:
    """Things that suggest a real, active business."""
    bonus = 0
    reasons: list[str] = []
    if (contact.get("services") or contact.get("enrichment", {}).get("services")):
        bonus += 5
        reasons.append("services list extracted")
    if contact.get("tagline") or contact.get("enrichment", {}).get("tagline"):
        bonus += 3
        reasons.append("tagline present (real homepage)")
    return bonus, reasons


def _anti_signals(contact: dict) -> tuple[int, list[str]]:
    """Penalties — things that strongly correlate with wasted spend."""
    penalty = 0
    negs: list[str] = []
    if contact.get("opted_out"):
        penalty -= 200   # hard cold
        negs.append("explicitly opted out — DO NOT contact")
    if (contact.get("outreach_count") or 0) >= 3:
        penalty -= 15
        negs.append(f"contacted {contact.get('outreach_count')}× already — no reply")
    if not contact.get("phone") and not contact.get("email"):
        penalty -= 20
        negs.append("no phone, no email")
    rating = contact.get("rating")
    if rating is not None and rating < 3.0:
        penalty -= 10
        negs.append(f"Maps rating {rating} below 3.0")
    return penalty, negs


# ─── Public API ──────────────────────────────────────────────────────────────

def score_lead(contact: dict, enrichment: Optional[dict] = None) -> LeadScore:
    """Produce a Hot/Warm/Cold verdict for one contact.

    `contact` is the Mongo doc (or stub from discovery). `enrichment` is the
    optional payload from tools/enrichment.py — pass it when fresh, otherwise
    we read whatever's on the contact doc.
    """
    enrichment = enrichment or contact.get("enrichment") or {}

    # Base score from the existing scorer (rating + phone + website + category)
    base = score_contact(
        vertical=contact.get("vertical") or "",
        rating=contact.get("rating"),
        has_phone=bool(contact.get("phone")),
        has_website=bool(contact.get("website")),
        category=contact.get("category"),
        outreach_count=contact.get("outreach_count") or 0,
    )

    score = base
    reasons: list[str] = []
    negatives: list[str] = []

    # Surface what already counted toward the base score
    if contact.get("rating"):
        reasons.append(f"Maps rating {contact['rating']}")
    if contact.get("phone"):
        reasons.append("phone on file")
    if contact.get("website"):
        reasons.append("website on file")
    cat = (contact.get("category") or "").lower()
    targets = HIGH_VALUE_CATEGORIES.get(contact.get("vertical") or "", set())
    if cat and cat in targets:
        reasons.append(f"high-value category: {cat}")

    # Layer in richer signals
    em_bonus, em_reason = _email_quality_bonus(contact.get("email"))
    score += em_bonus
    if em_reason:
        reasons.append(em_reason)

    dm_bonus, dm_reason = _decision_maker_bonus(contact, enrichment)
    score += dm_bonus
    if dm_reason:
        reasons.append(dm_reason)

    rec_bonus, rec_reason = _recency_bonus(contact)
    score += rec_bonus
    if rec_reason and rec_bonus > 0:
        reasons.append(rec_reason)
    elif rec_reason and rec_bonus < 0:
        negatives.append(rec_reason)

    sig_bonus, sig_reasons = _signal_bonus(contact)
    score += sig_bonus
    reasons.extend(sig_reasons)

    act_bonus, act_reasons = _activity_signals(contact)
    score += act_bonus
    reasons.extend(act_reasons)

    pen, pen_negs = _anti_signals(contact)
    score += pen
    negatives.extend(pen_negs)

    # Clamp + verdict
    score = max(0, min(120, score))
    if score >= HOT_THRESHOLD:
        verdict = "hot"
    elif score >= WARM_THRESHOLD:
        verdict = "warm"
    else:
        verdict = "cold"

    return LeadScore(score=score, verdict=verdict, reasons=reasons, negatives=negatives)


# ─── Convenience: rank a list of contacts ────────────────────────────────────

def rank_contacts(contacts: list[dict]) -> list[dict]:
    """Score and sort: hot first, then warm, then cold. Returns the same dicts
    with `quality_score` and `quality_verdict` keys merged in for caller use.
    """
    ranked = []
    for c in contacts:
        ls = score_lead(c)
        c["quality_score"] = ls.score
        c["quality_verdict"] = ls.verdict
        c["quality_reasons"] = ls.reasons
        c["quality_negatives"] = ls.negatives
        ranked.append(c)
    rank_key = {"hot": 0, "warm": 1, "cold": 2}
    ranked.sort(key=lambda c: (rank_key.get(c["quality_verdict"], 3), -c["quality_score"]))
    return ranked
