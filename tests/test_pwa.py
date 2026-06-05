"""PWA wiring for the client portal — manifest, icons, service worker, head tags.

Pure file checks (no app/DB), so they run in CI and catch a broken manifest,
a missing icon, or the portal losing its install hooks.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def test_manifest_is_valid_and_complete():
    data = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert data["start_url"] == "/app"
    assert data["display"] == "standalone"
    assert data["scope"] == "/"
    assert data.get("theme_color") and data.get("background_color")
    sizes = {i["sizes"] for i in data["icons"]}
    assert {"192x192", "512x512"} <= sizes, "PWA needs 192 + 512 icons to be installable"


def test_icons_exist_and_are_real_pngs():
    for size in (192, 512):
        p = STATIC / "icons" / f"icon-{size}.png"
        assert p.exists(), f"missing icon {p.name}"
        blob = p.read_bytes()
        assert blob[:8] == PNG_SIG, f"{p.name} is not a valid PNG"
        assert len(blob) > 100


def test_service_worker_is_conservative():
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    for hook in ("install", "activate", "fetch"):
        assert f'addEventListener("{hook}"' in sw, f"sw missing {hook} handler"
    # money-sensitive: navigations must be network-first, never cache-first
    assert "navigate" in sw and "network" in sw.lower()


def test_portal_head_has_install_hooks():
    html = (ROOT / "templates" / "portal.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert 'navigator.serviceWorker.register("/sw.js")' in html
    assert 'localStorage.setItem("eyo_portal_token"' in html


def test_launcher_template_exists():
    html = (ROOT / "templates" / "app_launcher.html").read_text(encoding="utf-8")
    assert 'href="/static/manifest.webmanifest"' in html
    assert "eyo_portal_token" in html
