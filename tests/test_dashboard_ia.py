"""
Guardrails for the 8-tab admin dashboard IA (DASHBOARD_IA.md).

Pure text/parse checks on templates/dashboard.html — no app/DB needed. These
catch the two ways the reflow IA silently breaks: a `data-reflow` target with no
matching pane body, or a sidebar tab whose pane disappears.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"
HTML = DASH.read_text(encoding="utf-8")


def test_template_parses():
    import jinja2
    jinja2.Environment().parse(HTML)  # raises on malformed Jinja/blocks


@pytest.mark.parametrize("ssn", [
    "ssn-overview", "ssn-clients", "ssn-approvals", "ssn-activate",
    "ssn-growth", "ssn-ai", "ssn-billing", "ssn-tools",
])
def test_eight_sidebar_tabs_present(ssn):
    assert f'id="{ssn}"' in HTML, f"sidebar item {ssn} missing"


@pytest.mark.parametrize("pane", ["tab-overview", "tab-clients", "tab-approvals",
                                   "tab-activate", "tab-growth", "tab-ai",
                                   "tab-billing", "tab-tools"])
def test_each_tab_has_a_pane(pane):
    assert f'id="{pane}"' in HTML, f"pane #{pane} missing"


def test_every_reflow_target_has_a_body():
    """Each data-reflow='X' must land in an existing '#X-reflow-body'."""
    targets = set(re.findall(r'data-reflow="([a-z]+)"', HTML))
    assert targets, "no data-reflow tags found — reflow IA removed?"
    for t in targets:
        assert f'id="{t}-reflow-body"' in HTML, \
            f'data-reflow="{t}" has no #{t}-reflow-body container'


def test_reflow_runs_on_load():
    assert "function reflowDashboard()" in HTML
    assert "reflowDashboard()" in HTML.split("function reflowDashboard()", 1)[1], \
        "reflowDashboard is defined but never called"


def test_no_malformed_reflow_attrs():
    """Every `data-reflow=` must be a properly quoted lowercase value.

    The happy-path regex in test_every_reflow_target_has_a_body requires a
    closing quote, so a typo'd `data-reflow="growth>` (missing quote) slips
    past it while silently breaking the panel's DOM nesting. Catch it here.
    """
    total = len(re.findall(r'data-reflow=', HTML))
    good = len(re.findall(r'data-reflow="[a-z]+"', HTML))
    assert total == good, (
        f'{total - good} malformed data-reflow attribute(s) '
        '(missing/typo quote — must be data-reflow="lowercase")'
    )


def test_authheaders_is_defined():
    """~120 loaders call authHeaders(); without a global definition every one
    throws ReferenceError and its panel never loads (e.g. Outreach Analytics)."""
    assert "function authHeaders(" in HTML, "global authHeaders() helper missing"


@pytest.mark.parametrize("dead_nav", [
    "switchTabByName('tower')",
    "switchTabByName('attention')",
    'clientsNav("tower"',
])
def test_no_dead_nav_to_retired_panes(dead_nav):
    """#tab-tower and #tab-attention are reflow-source shells only. Nothing should
    navigate to them or the operator lands on a blank pane."""
    assert dead_nav not in HTML, f"dead nav to a retired pane still present: {dead_nav}"


def test_retired_panes_are_hidden_reflow_sources():
    """Both source shells must be display:none so they can never show as a tab."""
    for pane in ("tab-tower", "tab-attention"):
        m = re.search(rf'id="{pane}"[^>]*', HTML)
        assert m and "display:none" in m.group(0), f"#{pane} must be display:none"


def test_old_simpler_roster_removed():
    """The Clients tab should have ONE roster (the rich operator view that reflows
    in). The older roster-table/roster-tbody must be gone."""
    assert 'id="roster-table"' not in HTML, "old simpler roster-table still present"
    assert 'id="roster-tbody"' not in HTML, "old roster-tbody still present"


def test_design_tokens_present():
    """Phase 1 design-system tokens must exist in :root."""
    for tok in ("--r-md:", "--s3:", "--line:", "--surface:"):
        assert tok in HTML, f"design token {tok} missing from :root"


def test_canonical_orange_is_ff5c00():
    """Accent is canonicalised to #ff5c00 (97x in use + brand/marketing)."""
    assert "--accent: #ff5c00" in HTML, "canonical --accent must be #ff5c00"


@pytest.mark.parametrize("primitive", [
    ".card {", ".panel-title {", ".toolbar {", ".badge {", ".kpi {",
    ".btn--primary {", ".btn--ghost {", ".btn--ok ", ".btn--danger ",
    ".card--placeholder {", ".soon-tag {", ".tab-intro-title {",
])
def test_design_primitives_defined(primitive):
    style = HTML.split("</style>")[0]
    assert primitive in style, f"design primitive {primitive!r} not defined in <style>"


# Regression budget: these counts may only trend DOWN as screens migrate to the
# primitives. Bump the ceiling DOWN (never up) after each migration phase.
INLINE_BUTTON_CEILING = 145
ADHOC_CARD_CEILING = 183


def test_inline_styling_does_not_regrow():
    inline_buttons = len(re.findall(r'<button[^>]*style="', HTML))
    adhoc_cards = len(re.findall(r'style="[^"]*background[^"]*border[^"]*border-radius', HTML))
    assert inline_buttons <= INLINE_BUTTON_CEILING, (
        f"inline-styled buttons grew to {inline_buttons} (ceiling {INLINE_BUTTON_CEILING}); "
        "use .btn / .btn--* instead of inline styles")
    assert adhoc_cards <= ADHOC_CARD_CEILING, (
        f"ad-hoc card divs grew to {adhoc_cards} (ceiling {ADHOC_CARD_CEILING}); "
        "use .card instead of inline background+border+radius")


def test_tower_back_control_present():
    """Deep subsection panes carry a Back control built on the shared primitives."""
    style = HTML.split("</style>")[0]
    assert ".tower-back" in style, ".tower-back style not defined"
    backs = HTML.count('class="btn btn--ghost btn--sm tower-back"')
    assert backs == 7, f"expected 7 Back controls on subsection panes, found {backs}"
    assert 'onclick="towerBack()"' in HTML


def test_tower_nav_state_and_hash():
    """Nav stack + hash mirroring exist and both pane-showing functions record state."""
    for fn in ("function towerRecord(", "function towerBack(", "function towerGo("):
        assert fn in HTML, f"{fn} missing"
    assert 'history.replaceState(null, "", "#" + state)' in HTML, "hash not mirrored from state"
    assert "towerRecord(name)" in HTML, "switchTab does not record tower state"
    assert "towerRecord(panelName)" in HTML, "_subNavSwitch does not record tower state"
    # bookmark/share: a valid #state hash is honoured on load
    assert "_TOWER_STATES.has(h)" in HTML, "hash-on-load navigation missing"


def test_tower_back_fallback_is_command_center():
    """With an empty stack, Back returns to Command Center (overview)."""
    assert '_towerStack.pop() || "overview"' in HTML


def test_no_duplicate_static_ids():
    """Duplicate element IDs silently break getElementById (returns the first in
    DOM order). Ignore dynamic template-literal IDs like id="apf-${id}" — only
    static IDs must be unique. (Caught the ob-plan onboarding-modal bug.)"""
    from collections import Counter
    static_ids = [v for v in re.findall(r'\sid="([^"]+)"', HTML) if "$" not in v and "{" not in v]
    dups = {k: n for k, n in Counter(static_ids).items() if n > 1}
    assert not dups, f"duplicate static element id(s): {dups}"


def test_rich_roster_reflows_into_clients():
    """The rich operator roster (#ct-client-grid) must carry data-reflow='clients'
    so it lands in the Clients tab (its container is the source shell)."""
    block = HTML[HTML.index("Client Roster") - 200: HTML.index("Client Roster") + 200]
    assert 'data-reflow="clients"' in block, "rich roster not tagged to reflow into Clients"
