"""
Guardrails for the warm client portal (portal.html) design system — Phase 4.

Pure text/parse checks: the portal must parse, expose the shared primitive
classes (warm-valued), use the terracotta accent, and carry no dark CSS-rule
card backgrounds on its cream theme.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "templates" / "portal.html"
HTML = PORTAL.read_text(encoding="utf-8")


def test_portal_parses():
    import jinja2
    jinja2.Environment().parse(HTML)


@pytest.mark.parametrize("primitive", [
    ".card {", ".panel-title {", ".toolbar {", ".btn {",
    ".btn--primary {", ".btn--ghost {", ".badge {", ".empty-state {",
])
def test_portal_primitives_defined(primitive):
    style = HTML.split("</style>")[0]
    assert primitive in style, f"warm primitive {primitive!r} not defined in portal <style>"


def test_portal_accent_is_warm():
    """Portal accent maps to the terracotta brand colour, not the admin orange."""
    assert "--accent: var(--orange)" in HTML


def test_portal_no_dark_card_rules():
    """Inline dark colours are remapped by the warm-override block, but CSS-rule
    backgrounds/borders are not — so they must be authored warm. Catches the
    dark-card-on-cream bug (e.g. the old .sc-kpi background:#141414)."""
    dark = re.compile(
        r'(background|border)\s*:\s*(#0[0-9a-f]{2,5}\b|#1[0-9a-f]{2,5}\b|rgba\(5,5,5)', re.I)
    bugs = [l.strip()[:80] for l in HTML.splitlines()
            if 'style="' not in l and dark.search(l)]
    assert not bugs, f"dark CSS-rule background/border on the warm portal: {bugs[:5]}"


# Regression budget (portal). Phase 4b migrated card wrappers/buttons to primitives;
# the 11 remaining are warm-tokenized form inputs/tiles (no dark hex).
PORTAL_INLINE_BUTTON_CEILING = 0
PORTAL_ADHOC_CARD_CEILING = 11


def test_portal_no_dark_inline_or_ff5500():
    """Phase 4b routed every #ff5500 through --accent and tokenised inline darks.
    No dark #0xxxxx backgrounds/borders and no raw #ff5500 should remain anywhere."""
    assert "#ff5500" not in HTML.lower(), "raw #ff5500 must route through var(--accent)"
    darkbg = re.findall(r'(?:background[^;:]*|border[^;:]*):\s*#0[0-9a-f]{3,5}\b', HTML)
    assert not darkbg, f"dark inline background/border on warm portal: {set(darkbg[:5])}"


def test_portal_inline_does_not_regrow():
    inline_buttons = len(re.findall(r'<button[^>]*style="', HTML))
    adhoc_cards = len(re.findall(r'style="[^"]*background[^"]*border[^"]*border-radius', HTML))
    assert inline_buttons <= PORTAL_INLINE_BUTTON_CEILING, (
        f"portal inline-styled buttons grew to {inline_buttons} "
        f"(ceiling {PORTAL_INLINE_BUTTON_CEILING}); use .btn / .btn--*")
    assert adhoc_cards <= PORTAL_ADHOC_CARD_CEILING, (
        f"portal ad-hoc card divs grew to {adhoc_cards} "
        f"(ceiling {PORTAL_ADHOC_CARD_CEILING}); use .card")


# ── Redesigned IA guards (client dashboard simplification) ───────────────────

EXPECTED_TABS = ["today", "money", "approvals", "customers", "settings", "reports"]


def test_one_panel_per_tab():
    """Each tab maps to exactly one <section class="tabpanel" data-tab="X"> — no
    fragmented/duplicate panels (the pre-refactor portal had 2x today/money/reports)."""
    from collections import Counter
    panels = re.findall(r'<section class="tabpanel[^"]*" data-tab="([a-z]+)"', HTML)
    counts = Counter(panels)
    assert set(counts) == set(EXPECTED_TABS), (
        f"tabs present {sorted(counts)} != expected {sorted(EXPECTED_TABS)}")
    dupes = {t: n for t, n in counts.items() if n != 1}
    assert not dupes, f"each tab must have exactly one panel; duplicates: {dupes}"


def test_no_prospect_os_language_in_client_portal():
    """The paying-client portal must not surface internal Prospect-OS / lead-gen
    framing — rating, lead score, outreach activity, prospecting."""
    banned = [
        "Outreach Activity", "lead_score", "lead score", "Lead Quality",
        "Prospect OS", "Missed Opportunity Radar",
    ]
    low = HTML.lower()
    found = [b for b in banned if b.lower() in low]
    assert not found, f"internal/prospecting language in client portal: {found}"


def test_today_panel_has_core_surfaces():
    """Today must answer: WhatsApp status, Owner Brief, what needs you, what EYO did."""
    for marker in ('id="wa-pill"', 'id="owner-brief-card"',
                   'id="today-needs-body"', 'id="eyo-recap-body"'):
        assert marker in HTML, f"Today panel missing {marker}"


def test_demo_shim_is_gated():
    """The sample-data fetch shim must be wrapped in {% if demo %} so real client
    portals never ship it."""
    assert "{% if demo %}" in HTML and "window.fetch = function" in HTML, \
        "demo shim present"
    # The shim must sit inside the demo guard, not in the always-on path.
    before_guard = HTML.split("{% if demo %}")[0]
    assert "window.fetch = function" not in before_guard, \
        "fetch override must be inside the {% if demo %} block"
