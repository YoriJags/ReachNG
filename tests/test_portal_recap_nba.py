"""
Guards for the two portal data surfaces filled in after the IA refactor:
  - vault list next-best-action (deterministic, no LLM)
  - /recap composition ("what EYO did since yesterday")
"""
from __future__ import annotations

import os

os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/reachng_test")

from services.vault import _nba_from_text  # noqa: E402
import services.portal_feeds as pf  # noqa: E402


# ─── Next best action ─────────────────────────────────────────────────────────

def test_nba_occasion_beats_generic():
    out = _nba_from_text("customer loves a big birthday party", 0, None).lower()
    assert "birthday" in out


def test_nba_pricing_question():
    out = _nba_from_text("asked how much the vip table costs", 0, None).lower()
    assert "quote" in out or "pricing" in out


def test_nba_complaint():
    out = _nba_from_text("was angry about a refund last time", 0, None).lower()
    assert "goodwill" in out or "check in" in out


def test_nba_default_is_safe_string():
    out = _nba_from_text("", 0, None)
    assert isinstance(out, str) and out


# ─── Recap composition ────────────────────────────────────────────────────────

def test_recap_composes_lines(monkeypatch):
    monkeypatch.setattr(pf, "savings_for",
                        lambda name, days=1: {"messages_handled": 10, "hours_saved": 0.7})
    import tools.cash_signals as cs
    monkeypatch.setattr(cs, "cash_signals_for",
                        lambda name: {"cash_received_overnight_ngn": 250000,
                                      "hot_replies_overnight": 2,
                                      "asked_price_no_quote": 1})
    out = pf.recap_for("Demo Lounge", days=1)
    assert out["messages_handled"] == 10
    assert out["received_ngn"] == 250000
    joined = " ".join(out["lines"]).lower()
    assert "message" in joined
    assert "received" in joined
    assert "hot lead" in joined
    assert "price enquiry" in joined or "price enquiries" in joined


def test_recap_quiet_when_nothing(monkeypatch):
    monkeypatch.setattr(pf, "savings_for",
                        lambda name, days=1: {"messages_handled": 0, "hours_saved": 0})
    import tools.cash_signals as cs
    monkeypatch.setattr(cs, "cash_signals_for", lambda name: {})
    out = pf.recap_for("Demo Lounge", days=1)
    assert out["lines"] == []  # frontend renders the "quiet night" fallback
