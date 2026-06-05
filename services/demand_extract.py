"""Demand extraction — turn one inbound message into a normalized demand signal.

This is the upstream data source EYO Radar (services/demand_radar.py) needs:
Radar aggregates {topic, price_ask, quote_sent} items by topic with a 3-mention
floor, so the job here is NOT perfect NLP — it's CONSISTENT normalization. Two
customers asking "how much for the 2 bedroom?" and "price of 2-bedroom?" must
both land on the topic "2 bedroom" so they aggregate; a one-off mis-parse never
reaches 3 mentions and harmlessly drops out.

Pure + deterministic (no LLM, no DB) so it's fully testable and free to run on
every inbound. A Haiku enrichment can later sit behind the same extract_demand()
seam without changing callers.
"""
from __future__ import annotations

import re
from typing import Optional

# Price-ask tells (also gate "is this a demand at all").
_PRICE_TOKENS = (
    "how much", "price", "pricing", "rate", "rates", "cost", "costs", "fee",
    "fees", "quote", "tariff", "naira", "₦", "ngn", "how far na",
)

# Non-price demand markers ("do you have X", "looking for X", Pidgin "una get X").
_DEMAND_MARKERS = (
    "do you have", "do you sell", "do you stock", "do you offer", "do you do",
    "you get", "una get", "do una", "looking for", "i need", "i want",
    "interested in", "searching for", "available", "you dey sell", "abeg i want",
)

# Topic-capture patterns (ordered; first match wins). group "t" = raw topic.
_PATTERNS = [
    re.compile(r"(?:price|cost|rate|tariff|fee)s?\s+(?:of|for)\s+(?P<t>.+)", re.I),
    re.compile(r"how much\s+(?:is|for|are|does|to)?\s*(?P<t>.+)", re.I),
    re.compile(r"do (?:you|una)\s+(?:have|sell|stock|offer|do|get)\s+(?:any\s+)?(?P<t>.+)", re.I),
    re.compile(r"(?:you|una)\s+(?:dey sell|get)\s+(?P<t>.+)", re.I),
    re.compile(r"(?:i'?m |i am )?(?:looking|searching) for\s+(?P<t>.+)", re.I),
    re.compile(r"(?:i )?(?:need|want)\s+(?:a |an |some )?(?P<t>.+)", re.I),
    re.compile(r"interested in\s+(?P<t>.+)", re.I),
    re.compile(r"(?:is |are |you get |una get )?(?P<t>.+?)\s+available", re.I),
]

# Stripped from the edges of a captured topic.
_EDGE_STOP = {
    "the", "a", "an", "your", "my", "some", "any", "that", "this", "of", "for",
    "do", "you", "una", "get", "have", "sell", "to", "is", "are", "please",
    "abeg", "biko", "na", "o", "now", "today", "pls", "guy", "boss", "sir",
    "ma", "and", "or", "available", "still", "got",
}
# Hard cut: everything from these words onward is dropped (connectors/fillers).
_CUT = re.compile(
    r"\b(for|in|at|on|please|abeg|biko|today|tomorrow|available|how much|price|"
    r"cost|rate|nearby|around|here)\b", re.I)


def has_price_token(text: str) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in _PRICE_TOKENS)


def looks_like_demand(text: str) -> bool:
    """Cheap gate: is this message asking for a product/service or a price?"""
    if not text:
        return False
    t = text.lower()
    return has_price_token(t) or any(m in t for m in _DEMAND_MARKERS)


def _singularize(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        if word.endswith("ies"):
            return word[:-3] + "y"
        return word[:-1]
    return word


def normalize_topic(raw: str) -> Optional[str]:
    """Collapse a raw captured phrase to a stable 1-3 word topic, or None.

    Lowercase, strip edges/fillers, cut at the first connector, singularize the
    last word, and cap at 3 words so '2 bedroom flat in lekki' -> '2 bedroom flat'
    and 'flats' / 'flat' converge on 'flat'."""
    if not raw:
        return None
    s = raw.lower().strip()
    # Stop at sentence punctuation first.
    s = re.split(r"[?.!,;\n]", s, maxsplit=1)[0]
    # Drop everything from the first connector/filler onward.
    s = _CUT.split(s, maxsplit=1)[0]
    # Hyphens -> spaces so "2-bedroom" and "2 bedroom" converge on one topic.
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = [w for w in s.split(" ") if w]
    # Trim stopwords off both ends.
    while words and words[0] in _EDGE_STOP:
        words.pop(0)
    while words and words[-1] in _EDGE_STOP:
        words.pop()
    if not words:
        return None
    words = words[:3]
    words[-1] = _singularize(words[-1])
    topic = " ".join(words).strip()
    if len(topic) < 2:
        return None
    return topic


def extract_demand(text: str) -> Optional[dict]:
    """Extract one demand signal from an inbound message.

    Returns {"topic": str, "price_ask": bool} or None when the message isn't a
    demand we can attribute to a topic.
    """
    if not looks_like_demand(text):
        return None
    price_ask = has_price_token(text)
    for pat in _PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        topic = normalize_topic(m.group("t"))
        if topic:
            return {"topic": topic, "price_ask": price_ask}
    return None
