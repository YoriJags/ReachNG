"""Demand extraction — the Radar data source. Pure, no DB/LLM.

The property that matters most: variants of the same ask must NORMALIZE to the
same topic so Radar's 3-mention floor aggregates them.
"""
from __future__ import annotations

import pytest

from services.demand_extract import (
    looks_like_demand, normalize_topic, extract_demand,
)


@pytest.mark.parametrize("msg", [
    "how much for the 2 bedroom?",
    "do you have ankara",
    "I'm looking for a 3 bedroom flat",
    "una get generator?",
    "price of jollof",
])
def test_demand_messages_detected(msg):
    assert looks_like_demand(msg) is True


@pytest.mark.parametrize("msg", [
    "thank you so much",
    "ok i will come tomorrow",
    "good morning",
    "",
])
def test_non_demand_messages_ignored(msg):
    assert looks_like_demand(msg) is False
    assert extract_demand(msg) is None


def test_price_ask_flag():
    assert extract_demand("how much for the 2 bedroom?")["price_ask"] is True
    d = extract_demand("do you have ankara")
    assert d["price_ask"] is False


@pytest.mark.parametrize("msg,topic", [
    ("how much for the 2 bedroom?", "2 bedroom"),
    ("price of 2-bedroom", "2 bedroom"),
    ("do you have ankara", "ankara"),
    ("do you sell ankara fabric", "ankara fabric"),
    ("una get generator?", "generator"),
    ("you dey sell rice?", "rice"),
    ("how much is jollof for 50 people", "jollof"),
    ("interested in the 3 bedroom flat in lekki", "3 bedroom flat"),
    ("is the apartment available?", "apartment"),
])
def test_topic_extraction(msg, topic):
    assert extract_demand(msg)["topic"] == topic


def test_variants_converge_for_aggregation():
    """The whole point: spelling/format variants land on ONE topic so Radar can
    count them together."""
    variants = [
        "how much for the 2 bedroom?",
        "price of 2-bedroom",
        "do you have a 2 bedroom",
        "looking for 2 bedrooms",     # plural -> singular
    ]
    topics = {extract_demand(v)["topic"] for v in variants}
    assert topics == {"2 bedroom"}, f"variants failed to converge: {topics}"


def test_plural_singularizes():
    assert normalize_topic("flats") == "flat"
    assert normalize_topic("babies") == "baby"
    assert normalize_topic("dress") == "dress"   # not over-stripped


def test_topic_capped_at_three_words():
    t = normalize_topic("big luxury 4 bedroom duplex mansion")
    assert len(t.split()) <= 3
