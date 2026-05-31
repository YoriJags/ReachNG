"""
Tests for the magic-potion features (Money Leak, Revenue Rescue, Readiness,
Speed Watch, resurrection HITL guarantee).

These exercise the real composition logic + route guards — not just imports.
Detectors are monkeypatched so the suite needs no live Mongo.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/reachng_test")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# ─── Money Leak composition (no DB) ───────────────────────────────────────────

def _patch_detectors(monkeypatch, *, collectible=0, collectible_count=0,
                     missed=None, promises=None, silent=None):
    import services.money_leak as ml
    monkeypatch.setattr(ml, "cash_signals_for", lambda n: {
        "collectible_total_ngn": collectible,
        "collectible_count": collectible_count,
        "breakdown": {"rent": {}, "debt": {}, "school_fees": {}},
    })
    monkeypatch.setattr(ml, "missed_opportunities_for", lambda *a, **k: missed or [])
    monkeypatch.setattr(ml, "_ghosted_promises", lambda *a, **k: promises or [])
    monkeypatch.setattr(ml, "_silent_inbound", lambda *a, **k: silent or [])
    return ml


def test_money_leak_empty(monkeypatch):
    ml = _patch_detectors(monkeypatch)
    rep = ml.money_leak_report("Empty Co")
    assert rep["total_ngn"] == 0
    assert rep["confirmed_ngn"] == 0
    assert rep["pipeline_ngn"] == 0
    assert rep["total_leak_count"] == 0
    assert len(rep["categories"]) == 4           # always the 4 buckets
    assert "0" in rep["headline"]


def test_money_leak_composition(monkeypatch):
    ml = _patch_detectors(
        monkeypatch,
        collectible=200_000, collectible_count=2,
        missed=[{"contact_name": "A", "phone": "+1", "reply_text": "how much?"}],
        promises=[{"contact_name": "B", "phone": "+2"}],
        silent=[],
    )
    rep = ml.money_leak_report("Test Co", avg_deal_ngn=50_000)
    assert rep["confirmed_ngn"] == 200_000
    assert rep["pipeline_ngn"] == 100_000        # (1 missed + 1 promise) * 50k
    assert rep["total_ngn"] == 300_000
    assert rep["total_leak_count"] == 4          # 2 confirmed + 1 + 1 + 0
    # Confirmed bucket is real ₦; pipeline buckets are estimates
    kinds = {c["key"]: c["kind"] for c in rep["categories"]}
    assert kinds["confirmed_owed"] == "confirmed"
    assert kinds["asked_price_no_quote"] == "pipeline"


def test_rescue_targets_dedup_and_priority(monkeypatch):
    import services.money_leak as ml

    def fake_report(name, days=30):
        return {"categories": [
            {"key": "silent_inbound",      "kind": "pipeline",
             "examples": [{"contact_name": "S", "phone": "+9"}]},
            {"key": "ghosted_promises",    "kind": "pipeline",
             "examples": [{"contact_name": "G", "phone": "+9"}]},   # dup phone
            {"key": "asked_price_no_quote","kind": "pipeline",
             "examples": [{"contact_name": "P", "phone": "+1"}]},
            {"key": "confirmed_owed",      "kind": "confirmed", "examples": []},
        ]}

    monkeypatch.setattr(ml, "money_leak_report", fake_report)
    targets = ml.rescue_targets("Test Co")
    phones = [t["phone"] for t in targets]
    assert phones[0] == "+9"          # ghosted_promises ranked first
    assert phones == ["+9", "+1"]     # silent dup of +9 removed; confirmed excluded


# ─── Route guards: bad token must never 200 (tenant isolation) ────────────────

@pytest.mark.parametrize("path", [
    "/portal/no-such-token-xyz/money-leak/data",
    "/portal/no-such-token-xyz/revenue-rescue",
    "/portal/no-such-token-xyz/readiness",
    "/portal/no-such-token-xyz/speed-watch",
])
def test_bad_token_rejected(client, monkeypatch, path):
    import api.portal as portal
    monkeypatch.setattr(portal, "_get_client_by_token", lambda t: None)
    r = client.get(path)
    assert r.status_code == 404, f"{path} must 404 on bad token, got {r.status_code}"


# ─── Resurrection / Revenue Rescue stays HITL ─────────────────────────────────

def test_resurrection_forces_hitl(client, monkeypatch):
    """The Revenue Rescue 'wake this money up' path must force HITL — drafts
    queue for approval, nothing auto-sends."""
    import api.portal as portal
    import api.b2c as b2c

    monkeypatch.setattr(portal, "_get_client_by_token",
                        lambda t: {"name": "Test Co", "vertical": "hospitality", "_id": "x"})

    captured = {}

    async def fake_run(client_name, body, background_tasks):
        captured["hitl_mode"] = body.hitl_mode
        captured["client_name"] = client_name
        return {"ok": True, "queued": 0}

    monkeypatch.setattr(b2c, "run_b2c_campaign", fake_run)

    r = client.post("/portal/run-resurrection/sometoken",
                    json={"dry_run": False, "max_contacts": 5})
    assert r.status_code == 200
    assert captured.get("hitl_mode") is True, "resurrection must force HITL mode"
    assert captured.get("client_name") == "Test Co"
