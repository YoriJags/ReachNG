"""EYO Radar — aggregate demand intelligence (invention #3). Pure checks."""
from __future__ import annotations

from services.demand_radar import build_radar, radar_headlines

ITEMS = (
    [{"topic": "jollof trays", "price_ask": True, "quote_sent": False}] * 6 +
    [{"topic": "small chops", "price_ask": True, "quote_sent": True}] * 4 +
    [{"topic": "vip table", "price_ask": False, "quote_sent": False}] * 3 +
    [{"topic": "", "price_ask": True}] * 2  # blank topics ignored
)


def test_aggregates_and_ignores_blank_topics():
    r = build_radar(ITEMS, min_mentions=1)
    topics = {s["topic"] for s in r["all_signals"]}
    assert topics == {"jollof trays", "small chops", "vip table"}
    jollof = next(s for s in r["all_signals"] if s["topic"] == "jollof trays")
    assert jollof["mentions"] == 6 and jollof["price_asks"] == 6


def test_ranks_most_price_asked_first():
    r = build_radar(ITEMS, min_mentions=1)
    assert r["signals"][0]["topic"] == "jollof trays"


def test_missing_price_flag():
    r = build_radar(ITEMS, known_prices=["small chops"], min_mentions=1)
    jollof = next(s for s in r["signals"] if s["topic"] == "jollof trays")
    small = next(s for s in r["signals"] if s["topic"] == "small chops")
    assert jollof["missing_price"] is True       # asked, no listed price
    assert small["missing_price"] is False        # has a known price


def test_unmet_quotes():
    r = build_radar(ITEMS, min_mentions=1)
    jollof = next(s for s in r["signals"] if s["topic"] == "jollof trays")
    small = next(s for s in r["signals"] if s["topic"] == "small chops")
    assert jollof["unmet_quotes"] == 6            # 6 asks, 0 quotes
    assert small["unmet_quotes"] == 0             # 4 asks, 4 quotes


def test_min_mentions_filter():
    r = build_radar(ITEMS, min_mentions=5)
    assert [s["topic"] for s in r["signals"]] == ["jollof trays"]


def test_headlines_are_action_oriented():
    r = build_radar(ITEMS, known_prices=["small chops"], min_mentions=1)
    lines = radar_headlines(r, top=3)
    assert any("no listed price" in l.lower() for l in lines)
    assert any("Jollof Trays" in l for l in lines)
