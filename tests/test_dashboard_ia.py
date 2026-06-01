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
