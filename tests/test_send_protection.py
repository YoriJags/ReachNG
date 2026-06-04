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
from tools.hitl import _enforce_whatsapp_consent_gate, OutreachConsentMissing  # noqa: E402
from tools import outreach  # noqa: E402


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
            requires_template=True, contact_name="Stranger Ltd",
        )


def test_cold_discovery_whatsapp_allowed_with_open_session():
    # They messaged in within 24h (requires_template False) → allowed.
    _enforce_whatsapp_consent_gate(
        source="maps", channel="whatsapp",
        requires_template=False, contact_name="Replied Co",
    )


def test_cold_discovery_email_not_gated():
    # Email is the cold channel — never blocked by this floor.
    _enforce_whatsapp_consent_gate(
        source="maps", channel="email",
        requires_template=True, contact_name="Cold Email Co",
    )


def test_byo_leads_whatsapp_not_gated():
    # BYO leads carry client-attested consent — not a cold-discovery source.
    _enforce_whatsapp_consent_gate(
        source="byo_leads", channel="whatsapp",
        requires_template=True, contact_name="Imported Customer",
    )


def test_transactional_whatsapp_not_gated():
    _enforce_whatsapp_consent_gate(
        source="invoice", channel="whatsapp",
        requires_template=True, contact_name="Known Debtor",
    )


# ─── WA-existence pre-check (off by default, fail-open) ───────────────────────

def test_existence_check_inert_when_flag_off(monkeypatch):
    monkeypatch.setattr(outreach, "get_settings",
                        lambda: SimpleNamespace(whatsapp_existence_check=False,
                                                unipile_dsn="d", unipile_api_key="k"))
    res = asyncio.run(outreach.check_whatsapp_exists("+2348010000000", "acc"))
    assert res is None  # indeterminate → caller proceeds
