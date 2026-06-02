"""
Guardrails for the ReachNG pre-launch premium outreach campaign (b2b_saas).

Pure-function tests — no DB, no network, no LLM. They lock the three things the
campaign depends on: premium lead scoring, the A/B/C variant system, and
graceful Maps discovery when the API key is missing.
"""
from __future__ import annotations

import asyncio

import pytest

from tools.lead_scorer import score_lead, premium_fit
from tools.ab_testing import assign_variant, VARIANTS
from services.reachng_self_outreach import VARIANT_STYLES, _style_directive


# ── Premium lead scoring ─────────────────────────────────────────────────────

def test_premium_restaurant_scores_hot():
    """A premium, WhatsApp-heavy, well-reviewed VI lounge is a hot lead."""
    biz = {
        "vertical": "b2b_saas",
        "name": "Cocoon Luxury Rooftop Lounge",
        "category": "Rooftop restaurant & lounge",
        "address": "Eko Atlantic, Victoria Island, Lagos",
        "rating": 4.6,
        "review_count": 120,
        "phone": "+2348012345678",
        "website": "https://cocoon.ng",
    }
    ls = score_lead(biz)
    assert ls.verdict == "hot"
    joined = " ".join(ls.reasons).lower()
    assert "whatsapp-heavy" in joined
    assert "premium" in joined


def test_tiny_low_fit_business_scores_cold():
    """Low rating, no website/phone, thin reviews → cold (dropped from campaign)."""
    biz = {
        "vertical": "b2b_saas",
        "name": "Mama Nkechi Provisions",
        "category": "Convenience store",
        "address": "Mushin, Lagos",
        "rating": 3.1,
        "review_count": 4,
    }
    ls = score_lead(biz)
    assert ls.verdict == "cold"


def test_premium_fit_gate():
    """rating>=4.3 AND reviews>=30; unknown review count passes on rating alone."""
    assert premium_fit({"rating": 4.6, "review_count": 120}) is True
    assert premium_fit({"rating": 4.0, "review_count": 100}) is False   # rating too low
    assert premium_fit({"rating": 4.5, "review_count": 10}) is False    # too few reviews
    assert premium_fit({"rating": 4.5, "review_count": None}) is True   # unknown → don't drop
    assert premium_fit({"rating": None}) is False


# ── A/B/C variant system ─────────────────────────────────────────────────────

def test_three_variants_exist():
    assert VARIANTS == ("A", "B", "C")
    assert set(VARIANT_STYLES) == {"A", "B", "C"}
    assert set(VARIANT_STYLES.values()) == {"founder", "money_leak", "owner_relief"}


def test_assign_variant_in_range():
    seen = {assign_variant() for _ in range(200)}
    assert seen <= {"A", "B", "C"} and seen, "assign_variant produced an out-of-range value"


def test_style_directive_resolves():
    for v in ("A", "B", "C"):
        assert _style_directive(v), f"variant {v} has no style directive"
    assert _style_directive(None) == ""
    assert _style_directive("Z") == ""   # unknown letter → neutral founder intro


# ── Discovery graceful failure ───────────────────────────────────────────────

def test_discovery_without_api_key_returns_empty(monkeypatch):
    """No GOOGLE_MAPS_API_KEY → discovery returns [] without firing requests."""
    import tools.discovery as d

    class _Settings:
        google_maps_api_key = None
        default_city = "Lagos, Nigeria"

    monkeypatch.setattr(d, "get_settings", lambda: _Settings())
    out = asyncio.run(d.discover_businesses("b2b_saas", max_results=5))
    assert out == []
