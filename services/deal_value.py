"""Per-lead deal value — the real pipeline-₦ source.

money_leak's pipeline figure (asked-price / ghosted-promise / silent) used a flat
₦50k per lead because nothing captured what a lead is actually worth. This module
provides a real per-contact value and the parser that captures it.

Two pieces:
  • parse_ngn(text)            — pull a ₦ amount out of a message (the quote EYO
                                 sends a customer). Conservative: only matches
                                 currency-cued / k-m-suffixed / comma-grouped
                                 numbers, so phone numbers and dates don't leak in.
  • deal_value_for_contact()   — resolve a contact's ₦ value: an explicit closed
                                 deal value > the last price we quoted them > a
                                 linked unit's rent (real estate) > a default.

Pure + deterministic (no DB) so it's fully testable; callers pass the contact doc.
"""
from __future__ import annotations

import re
from typing import Optional

DEFAULT_DEAL_NGN = 50_000
DEFAULT_CURRENCY = "NGN"

# Money is Naira-first (this is a Nigerian product) but NOT Naira-only: Lagos
# luxury real estate and diaspora deals are routinely quoted in USD/GBP/EUR, so
# the parser recognises those too and tags which currency it found.
_SYMBOL_TO_CCY = {
    "₦": "NGN", "n": "NGN", "ngn": "NGN", "naira": "NGN",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
}

_CCY = r"₦|\$|£|€|ngn|usd|gbp|eur|naira|dollars?|pounds?|euros?"
_NUM = r"\d[\d,]*(?:\.\d+)?"
# currency BEFORE the number ($50,000 / ₦2.5m / N50000)
_BEFORE = re.compile(rf"(?P<ccy>{_CCY}|\bn)\s*(?P<num>{_NUM})\s*(?P<suf>[km])?", re.I)
# currency AFTER the number (50,000 dollars / 2.5m naira)
_AFTER = re.compile(rf"(?P<num>{_NUM})\s*(?P<suf>[km])?\s*(?P<ccy>{_CCY})\b", re.I)
# no currency, accepted only if comma-grouped or k/m suffixed -> assumed NGN.
_PLAIN = re.compile(rf"\b(?P<num>{_NUM})\s*(?P<suf>[km])?\b", re.I)

_MIN = 1_000           # below this it's not a price (PINs, counts, "5 people")
_MAX = 1_000_000_000   # sanity ceiling


def _amount(num: str, suffix: Optional[str]) -> Optional[int]:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        v *= {"k": 1_000, "m": 1_000_000}[suffix.lower()]
    v = int(round(v))
    return v if _MIN <= v <= _MAX else None


def _ccy_code(token: Optional[str]) -> str:
    if not token:
        return DEFAULT_CURRENCY
    t = token.strip().lower()
    return _SYMBOL_TO_CCY.get(t) or _SYMBOL_TO_CCY.get(t.rstrip("s"), DEFAULT_CURRENCY)


def parse_money(text: str) -> Optional[dict]:
    """Largest plausible monetary amount in `text` as {"amount", "currency"}.

    A quote is usually the biggest figure in the message, so we return the max.
    Bare digit runs (phone numbers, dates) are ignored — an amount needs a
    currency symbol/word, a k/m suffix, or comma grouping. Currency defaults to
    NGN when only a number is given.
    """
    if not text:
        return None
    # (amount, currency, priority) — explicit currency beats a bare NGN default.
    cands: list[tuple[int, str, int]] = []
    for m in _BEFORE.finditer(text):
        v = _amount(m.group("num"), m.group("suf"))
        if v is not None:
            cands.append((v, _ccy_code(m.group("ccy")), 1))
    for m in _AFTER.finditer(text):
        v = _amount(m.group("num"), m.group("suf"))
        if v is not None:
            cands.append((v, _ccy_code(m.group("ccy")), 1))
    for m in _PLAIN.finditer(text):
        if "," not in m.group("num") and not m.group("suf"):
            continue  # bare digit run — not a price
        v = _amount(m.group("num"), m.group("suf"))
        if v is not None:
            cands.append((v, DEFAULT_CURRENCY, 0))
    if not cands:
        return None
    amount, currency, _ = max(cands, key=lambda c: (c[0], c[2]))
    return {"amount": amount, "currency": currency}


def parse_ngn(text: str) -> Optional[int]:
    """Back-compat: the amount when the quote is in Naira (or unmarked), else
    None. Foreign-currency quotes are captured by parse_money but not silently
    treated as Naira."""
    m = parse_money(text)
    if m and m["currency"] == "NGN":
        return m["amount"]
    return None


def _pos(v) -> Optional[int]:
    try:
        n = int(round(float(v)))
        return n if n >= _MIN else None
    except (TypeError, ValueError):
        return None


def deal_value_for_contact(contact: Optional[dict],
                           *, default_ngn: int = DEFAULT_DEAL_NGN) -> int:
    """Resolve a contact's pipeline ₦ value, most-specific first.

    explicit closed-deal value  >  last price we quoted them  >  linked unit rent
    (real estate)  >  default.
    """
    if not contact:
        return default_ngn
    for field in ("deal_value_ngn", "last_quote_ngn", "unit_rent_ngn"):
        v = _pos(contact.get(field))
        if v is not None:
            return v
    return default_ngn
