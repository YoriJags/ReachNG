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


# Regression budget (portal). Lower as inline cards/buttons migrate to .card/.btn.
PORTAL_INLINE_BUTTON_CEILING = 8
PORTAL_ADHOC_CARD_CEILING = 35


def test_portal_inline_does_not_regrow():
    inline_buttons = len(re.findall(r'<button[^>]*style="', HTML))
    adhoc_cards = len(re.findall(r'style="[^"]*background[^"]*border[^"]*border-radius', HTML))
    assert inline_buttons <= PORTAL_INLINE_BUTTON_CEILING, (
        f"portal inline-styled buttons grew to {inline_buttons} "
        f"(ceiling {PORTAL_INLINE_BUTTON_CEILING}); use .btn / .btn--*")
    assert adhoc_cards <= PORTAL_ADHOC_CARD_CEILING, (
        f"portal ad-hoc card divs grew to {adhoc_cards} "
        f"(ceiling {PORTAL_ADHOC_CARD_CEILING}); use .card")
