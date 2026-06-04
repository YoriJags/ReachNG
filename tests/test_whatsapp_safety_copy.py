"""
Slice 2 guardrails — honest WhatsApp account-safety language.

The client portal and the MSA must explain how we protect a client's number
WITHOUT over-promising. Specifically:
  - the portal carries a "How EYO protects your WhatsApp number" section
  - the MSA carries an acceptable-use clause + an explicit no-guarantee statement
  - neither claims "zero ban", "ban-proof", or a guarantee against suspension
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = (ROOT / "templates" / "portal.html").read_text(encoding="utf-8")
MSA = (ROOT / "legal" / "MSA.md").read_text(encoding="utf-8")

# Phrases that would be dishonest/over-promising about WhatsApp bans.
_BANNED_CLAIMS = [
    "zero ban", "zero-ban", "ban-proof", "banproof", "ban proof",
    "guaranteed delivery", "never be banned", "won't be banned",
    "cannot be banned", "no ban risk", "guarantee against",
]


def test_portal_has_protection_section():
    assert "How EYO protects your WhatsApp number" in PORTAL
    # The honest disclaimer must be present (no tool can guarantee).
    assert "can guarantee" in PORTAL.lower()


def test_msa_has_acceptable_use_and_no_guarantee():
    assert "WhatsApp messaging" in MSA
    assert "acceptable use" in MSA.lower()
    assert "No guarantee" in MSA
    # References the real safeguards, not vague assurances.
    assert "HITL" in MSA
    assert "warm-up" in MSA.lower()
    assert "opt-out rate exceeds 3%" in MSA


def test_no_overpromising_ban_claims():
    for text, label in [(PORTAL, "portal.html"), (MSA, "MSA.md")]:
        low = text.lower()
        for claim in _BANNED_CLAIMS:
            assert claim not in low, f"over-promising claim {claim!r} found in {label}"


def test_portal_still_parses():
    import jinja2
    jinja2.Environment().parse(PORTAL)
