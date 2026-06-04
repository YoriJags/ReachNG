"""
Slice 3 guardrails — Unipile send-path protection floor.

  - send window: automated sends held outside Africa/Lagos 08:00–20:00
  - consent floor: cold-discovery WhatsApp blocked unless a 24h session is open
  - WA-existence pre-check: off by default, fail-open

None of these weaken HITL — human approvals are never gated by the send window.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/reachng_test")

from tools.account_guard import is_within_send_window  # noqa: E402
from tools.hitl import _enforce_whatsapp_consent_gate, OutreachConsentMissing, _client_transport  # noqa: E402
from tools import outreach  # noqa: E402


# ─── Transport awareness (build #0) ───────────────────────────────────────────

class _FakeClients:
    def __init__(self, doc):
        self._doc = doc
    def find_one(self, query, projection=None):
        return self._doc


def test_client_transport_resolves_meta(monkeypatch):
    import api.clients as ac
    monkeypatch.setattr(ac, "get_clients", lambda: _FakeClients({"whatsapp_provider": "meta"}))
    assert _client_transport("Lex") == "meta"


def test_client_transport_defaults_unipile_when_unset(monkeypatch):
    import api.clients as ac
    # client exists (has _id) but no whatsapp_provider field set
    monkeypatch.setattr(ac, "get_clients", lambda: _FakeClients({"_id": "abc123"}))
    assert _client_transport("Altitude") == "unipile"


def test_client_transport_none_when_no_client(monkeypatch):
    import api.clients as ac
    monkeypatch.setattr(ac, "get_clients", lambda: _FakeClients(None))
    assert _client_transport("Ghost") is None
    assert _client_transport(None) is None


def _utc(h, m=0):
    return datetime(2026, 6, 4, h, m, tzinfo=timezone.utc)


# ─── Send window (Lagos = UTC+1, no DST) ──────────────────────────────────────

def test_send_window_open_midday():
    # 12:00 Lagos == 11:00 UTC
    assert is_within_send_window(_utc(11, 0)) is True


def test_send_window_closed_overnight():
    # 03:00 Lagos == 02:00 UTC
    assert is_within_send_window(_utc(2, 0)) is False


def test_send_window_boundaries():
    assert is_within_send_window(_utc(7, 0)) is True    # 08:00 Lagos — open
    assert is_within_send_window(_utc(6, 30)) is False  # 07:30 Lagos — closed
    assert is_within_send_window(_utc(19, 0)) is False  # 20:00 Lagos — closed (exclusive)
    assert is_within_send_window(_utc(18, 30)) is True  # 19:30 Lagos — open


# ─── Consent floor ────────────────────────────────────────────────────────────

def test_cold_discovery_whatsapp_blocked_without_session():
    with pytest.raises(OutreachConsentMissing):
        _enforce_whatsapp_consent_gate(
            source="maps", channel="whatsapp",
            has_open_session=False, contact_name="Stranger Ltd",
        )


def test_cold_discovery_whatsapp_allowed_with_open_session():
    # They messaged in within 24h (open session) → allowed.
    _enforce_whatsapp_consent_gate(
        source="maps", channel="whatsapp",
        has_open_session=True, contact_name="Replied Co",
    )


def test_cold_discovery_email_not_gated():
    # Email is the cold channel — never blocked by this floor.
    _enforce_whatsapp_consent_gate(
        source="maps", channel="email",
        has_open_session=False, contact_name="Cold Email Co",
    )


def test_byo_leads_whatsapp_not_gated():
    # BYO leads carry client-attested consent — not a cold-discovery source.
    _enforce_whatsapp_consent_gate(
        source="byo_leads", channel="whatsapp",
        has_open_session=False, contact_name="Imported Customer",
    )


def test_transactional_whatsapp_not_gated():
    _enforce_whatsapp_consent_gate(
        source="invoice", channel="whatsapp",
        has_open_session=False, contact_name="Known Debtor",
    )


# ─── WA-existence pre-check (off by default, fail-open) ───────────────────────

def test_existence_check_inert_when_flag_off(monkeypatch):
    monkeypatch.setattr(outreach, "get_settings",
                        lambda: SimpleNamespace(whatsapp_existence_check=False,
                                                unipile_dsn="d", unipile_api_key="k"))
    res = asyncio.run(outreach.check_whatsapp_exists("+2348010000000", "acc"))
    assert res is None  # indeterminate → caller proceeds
