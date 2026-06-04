"""
EYO Haggle — negotiation engine (invention #2). Pure deterministic checks.

The hard invariant: EYO never quotes below the owner's secret floor.
"""
from __future__ import annotations

from services.haggle import (
    negotiate, haggle_reply_text, owner_escalation_text,
    ACCEPT, COUNTER, SWEETEN, HOLD, ESCALATE,
)

RULES = {
    "list_price": 100000,
    "floor_price": 80000,
    "sweeteners": ["free delivery", "a complimentary bottle"],
    "max_rounds": 3,
}


def test_at_or_above_list_accepts():
    m = negotiate(RULES, customer_offer=100000)
    assert m["action"] == ACCEPT and m["price"] == 100000


def test_vague_ask_holds_and_sweetens_first():
    m = negotiate(RULES, customer_offer=None)
    assert m["action"] == SWEETEN
    assert m["price"] == 100000          # price held at list
    assert m["sweetener"] == "free delivery"


def test_offer_between_floor_and_list_counters_above_floor():
    m = negotiate(RULES, customer_offer=85000, state={"round": 0, "last_offer": 100000})
    assert m["action"] == COUNTER
    assert m["price"] >= RULES["floor_price"]   # never below floor
    assert m["price"] > 85000                    # countered above their offer


def test_never_quotes_below_floor_on_lowball():
    m = negotiate(RULES, customer_offer=50000)
    assert m["price"] >= RULES["floor_price"]
    assert m["below_floor_requested"] is True
    assert m["action"] in (SWEETEN, ESCALATE)


def test_lowball_escalates_when_sweeteners_exhausted_near_max():
    # Round 3 (== max_rounds): no sweetener round left -> escalate to owner
    m = negotiate(RULES, customer_offer=50000, state={"round": 2, "last_offer": 85000})
    assert m["action"] == ESCALATE
    assert m["price"] >= RULES["floor_price"]


def test_rounds_exhausted_escalates():
    m = negotiate(RULES, customer_offer=90000, state={"round": 3, "last_offer": 88000})
    assert m["action"] == ESCALATE


def test_small_gap_closes_the_deal_at_floor_or_above():
    # last_offer already near their offer -> accept, never below floor
    m = negotiate(RULES, customer_offer=88000, state={"round": 1, "last_offer": 89000})
    assert m["action"] == ACCEPT
    assert m["price"] >= RULES["floor_price"]


def test_reply_text_never_leaks_floor_and_phrases_each_move():
    for offer, st in [(None, None), (85000, {"round":0,"last_offer":100000}), (50000, None)]:
        m = negotiate(RULES, customer_offer=offer, state=st)
        txt = haggle_reply_text(m)
        assert "80000" not in txt and "80,000" not in txt   # floor never revealed
        assert txt  # always says something


def test_owner_escalation_text_mentions_floor_to_owner():
    txt = owner_escalation_text({"action": ESCALATE}, "Tunde", 50000, 80000)
    assert "80,000" in txt and "Tunde" in txt


def test_state_advances_round_and_tracks_last_offer():
    m = negotiate(RULES, customer_offer=85000, state={"round": 1, "last_offer": 95000})
    assert m["round"] == 2
    assert m["next_state"]["round"] == 2
    assert m["next_state"]["last_offer"] == m["price"]
