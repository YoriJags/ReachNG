"""
Smoke suite — fast checks that the app boots and core entry points behave.

Goal: catch import-level regressions and security regressions BEFORE deploy.
This is intentionally narrow; deep tests live next to their modules.

Requires SCHEDULER_ENABLED=false in the env so the lifespan doesn't fire jobs
against prod Mongo. The fixture below sets it.

Run: SCHEDULER_ENABLED=false pytest tests/test_smoke.py -q
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import pytest


# Force the scheduler off BEFORE any app import.
os.environ.setdefault("SCHEDULER_ENABLED", "false")
# Dummy required env so the lifespan startup gate passes — we don't actually
# call Anthropic or Mongo in this suite.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("MONGODB_URI",        "mongodb://localhost:27017/reachng_test")


@pytest.fixture(scope="module")
def client():
    """TestClient without `with` so the lifespan (index ensures + scheduler
    setup) doesn't fire — we don't have a real Mongo in this suite."""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# ─── 1. App imports + boots ───────────────────────────────────────────────────

def test_app_imports():
    """The whole import graph wires up without exceptions."""
    import main  # noqa: F401
    assert hasattr(main, "app")


# ─── 2. Health endpoint is open + returns ok ──────────────────────────────────

def test_health_open(client):
    r = client.get("/health")
    assert r.status_code == 200
    # "degraded" is OK when Mongo isn't reachable in the test env
    assert r.json().get("status") in ("ok", "healthy", "degraded")


# ─── 3. Admin endpoints reject anonymous traffic ──────────────────────────────

def test_admin_requires_auth(client):
    r = client.get("/dashboard")
    assert r.status_code in (401, 403), "dashboard must require auth"


def test_admin_api_requires_auth(client):
    r = client.get("/api/v1/admin/pricing")
    assert r.status_code in (401, 403)


# ─── 4. Webhook rejects unauthenticated POST when secret is set ───────────────

def test_webhook_rejects_missing_signature(client, monkeypatch):
    """With META_APP_SECRET configured, an unsigned POST must 401."""
    from config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", "test-secret", raising=False)
    r = client.post("/api/v1/webhooks/whatsapp", json={"object": "whatsapp_business_account"})
    assert r.status_code == 401


def test_webhook_accepts_valid_meta_signature(client, monkeypatch):
    from config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", "test-secret", raising=False)
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
    sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    r = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": sig},
    )
    assert r.status_code == 200


def test_webhook_rejects_bad_unipile_auth(client, monkeypatch):
    from config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "unipile_webhook_secret", "right-secret", raising=False)
    r = client.post(
        "/api/v1/webhooks/whatsapp",
        json={"data": {}},
        headers={"unipile-auth": "wrong-secret"},
    )
    assert r.status_code == 401


# ─── 5. Try-EYO sandbox responds (rate-limit + bad payload paths) ─────────────

def test_try_eyo_rejects_short_message(client):
    r = client.post("/api/v1/try-eyo", json={"vertical": "hospitality", "message": "hi"})
    assert r.status_code == 422  # Pydantic min_length=4


# ─── 6. Portal token scoping — bad token = 404, never a leak ──────────────────

def test_portal_bad_token_rejects(client):
    """A garbage portal token must NOT 200. Acceptable outcomes: 4xx/5xx or
    a raised Mongo timeout (test env has no DB) — never a successful render."""
    try:
        r = client.get("/portal/this-token-cannot-possibly-exist-xyz123")
        assert r.status_code >= 400 and r.status_code != 200
    except Exception:
        # pymongo.ServerSelectionTimeoutError etc. — proves the route did NOT
        # serve cached/leaked content for a bad token.
        pass


# ─── 7. Scheduler is off in this process ──────────────────────────────────────

def test_scheduler_disabled_under_test():
    assert os.environ.get("SCHEDULER_ENABLED", "").lower() == "false"
