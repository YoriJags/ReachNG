"""EYO Referral — word-of-mouth loop (invention #5). Pure checks."""
from __future__ import annotations

from services.referral import (
    should_ask_referral, mint_referral_code, referral_ask_text, DEFAULT_DELAY_HOURS,
)


def test_asks_after_a_clean_win():
    assert should_ask_referral(outcome_status="win", sentiment="happy") is True


def test_never_asks_on_a_loss():
    assert should_ask_referral(outcome_status="miss") is False


def test_never_asks_unhappy_customer():
    assert should_ask_referral(outcome_status="win", sentiment="angry") is False


def test_never_asks_twice():
    assert should_ask_referral(outcome_status="win", already_asked=True) is False


def test_min_value_gate():
    assert should_ask_referral(outcome_status="win", deal_value_ngn=5000, min_value_ngn=50000) is False
    assert should_ask_referral(outcome_status="win", deal_value_ngn=90000, min_value_ngn=50000) is True


def test_code_is_deterministic_and_idempotent():
    a = mint_referral_code("Altitude Lagos", "2348031234567")
    b = mint_referral_code("Altitude Lagos", "2348031234567")
    assert a == b                      # idempotent — no duplicate codes
    assert a.startswith("REF") and len(a) == 9
    # different referrer -> different code
    assert mint_referral_code("Altitude Lagos", "2348039999999") != a


def test_ask_text_has_name_reward_and_link():
    txt = referral_ask_text("Tunde", reward="you both get 10% off", link="https://reachng.ng/hi/abc")
    assert "Tunde" in txt
    assert "10% off" in txt
    assert "reachng.ng/hi/abc" in txt


def test_delay_default_exists():
    assert DEFAULT_DELAY_HOURS >= 1
