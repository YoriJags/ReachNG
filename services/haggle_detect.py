"""Detect a haggle in an inbound message + pull the customer's counter-offer.

Pure (no DB/LLM). Deliberately specific markers so ordinary messages don't read
as haggling; the wire further gates on a matching priced product, so a stray
match without a price is a harmless no-op.
"""
from __future__ import annotations

import re
from typing import Optional

from services.deal_value import parse_ngn
from services.demand_extract import extract_demand, normalize_topic

# Haggle messages often name the product as "for the X" rather than in a demand
# shape ("can you do 2m for the 2 bedroom"), so we fall back to this.
_FOR_PRODUCT = re.compile(r"\bfor\s+(?:the\s+|a\s+|an\s+)?(?P<t>[a-z0-9][a-z0-9\s\-]{1,40})", re.I)

# Phrases that signal price pushback. Specific on purpose (no bare "off"/"less").
_HAGGLE_MARKERS = (
    "last price", "best price", "final price", "your last", "how much last",
    "na how much last", "last last", "any discount", "discount", "reduce am",
    "abeg reduce", "reduce small", "reduce the price", "cheaper", "too expensive",
    "too much money", "too costly", "anything less", "can you do", "do better",
    "best you can do", "lower the price", "bring am down", "negotiate", "haggle",
    "consider me", "do me well", "no be small money",
)


def is_haggle(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(m in t for m in _HAGGLE_MARKERS)


def extract_offer(text: str) -> Optional[int]:
    """The price the customer is proposing, if they named one (NGN). A vague
    'last price?' has no number -> None, which the core handles as a value-add."""
    return parse_ngn(text)


def haggle_topic(text: str) -> Optional[str]:
    """Which product they're haggling over. Try the demand topic extractor first,
    then a haggle-specific 'for the X' fallback."""
    d = extract_demand(text)
    if d:
        return d["topic"]
    m = _FOR_PRODUCT.search(text or "")
    if m:
        return normalize_topic(m.group("t"))
    return None
