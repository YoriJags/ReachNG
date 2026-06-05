"""Per-lead deal value — ₦ parser + contact resolver. Pure."""
from __future__ import annotations

import pytest

from services.deal_value import (
    parse_ngn, parse_money, deal_value_for_contact, DEFAULT_DEAL_NGN,
)


@pytest.mark.parametrize("text,amount", [
    ("the 2 bedroom is ₦2,500,000/year", 2_500_000),
    ("it's ₦2.5m", 2_500_000),
    ("just 500k", 500_000),
    ("N50,000 deposit", 50_000),
    ("ngn 250000 balance", 250_000),
    ("price is 2,500,000 naira", 2_500_000),
    ("deposit ₦50k, balance 2.5m", 2_500_000),   # returns the largest
])
def test_parses_real_amounts(text, amount):
    assert parse_ngn(text) == amount


@pytest.mark.parametrize("text", [
    "call me on 08031234567",     # phone — no currency cue, no comma, no suffix
    "see you in 2026",            # year
    "50 people for the party",    # count
    "my pin is 1234",
    "N500 only",                  # below the ₦1,000 floor
    "",
    "no numbers here",
])
def test_ignores_non_prices(text):
    assert parse_ngn(text) is None


@pytest.mark.parametrize("text,amount,ccy", [
    ("the flat is $50,000", 50_000, "USD"),
    ("£200,000 for the house", 200_000, "GBP"),
    ("€1.5m", 1_500_000, "EUR"),
    ("50,000 dollars", 50_000, "USD"),
    ("2.5m naira", 2_500_000, "NGN"),
    ("₦2,500,000", 2_500_000, "NGN"),
    ("just 500k", 500_000, "NGN"),        # unmarked -> defaults NGN
])
def test_parse_money_is_currency_aware(text, amount, ccy):
    m = parse_money(text)
    assert m == {"amount": amount, "currency": ccy}


def test_parse_ngn_ignores_foreign_currency():
    # parse_money captures it; parse_ngn must NOT treat $ as ₦
    assert parse_money("$50,000")["currency"] == "USD"
    assert parse_ngn("$50,000") is None
    assert parse_ngn("₦50,000") == 50_000


def test_resolver_prefers_explicit_then_quote_then_unit():
    assert deal_value_for_contact({"deal_value_ngn": 300_000,
                                   "last_quote_ngn": 250_000}) == 300_000
    assert deal_value_for_contact({"last_quote_ngn": 250_000,
                                   "unit_rent_ngn": 1_200_000}) == 250_000
    assert deal_value_for_contact({"unit_rent_ngn": 1_200_000}) == 1_200_000


def test_resolver_skips_zero_and_falls_back():
    assert deal_value_for_contact({"deal_value_ngn": 0,
                                   "last_quote_ngn": 250_000}) == 250_000
    assert deal_value_for_contact({}) == DEFAULT_DEAL_NGN
    assert deal_value_for_contact(None) == DEFAULT_DEAL_NGN
    # a junk sub-floor value is ignored, not used
    assert deal_value_for_contact({"last_quote_ngn": 500}) == DEFAULT_DEAL_NGN


def test_custom_default():
    assert deal_value_for_contact(None, default_ngn=123_000) == 123_000
