"""Per-client MCP connections — the registry that lets EYO reach a client's own
tools (Google Calendar, Zoho CRM, Sheets...) through their MCP server.

A connection = {client_name, provider, url, auth_type, token (encrypted)}. The
bearer token is encrypted at rest with Fernet (EMAIL_CRED_KEY) via
``services.crypto`` — same fail-safe rule as email creds: no key => refuse to
store, never plaintext.

Tenant isolation (P0): every read/write is scoped by ``client_name``. A
connection registered for one landlord is never visible to another.

This is the SEAM, not a live agent. Nothing here does anything unless
``settings.mcp_actions_enabled`` is on AND a client has actually registered an
enabled connection. See docs/MCP_ACTIONS.md.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog
from pymongo import ASCENDING

from config import get_settings
from database import get_db
from services import crypto

log = structlog.get_logger()

# Providers we have a human label / connector pattern for. Not a hard allowlist —
# any URL-reachable MCP server works — just used for nicer display + the roster
# mapping (Scheduler=google_calendar, Reconciler=google_sheets, Paralegal=google_drive).
KNOWN_PROVIDERS = {
    "google_calendar": "Google Calendar",
    "google_sheets":   "Google Sheets",
    "google_drive":    "Google Drive",
    "gmail":           "Gmail",
    "zoho_crm":        "Zoho CRM",
    "notion":          "Notion",
}


def provider_label(provider: str) -> str:
    return KNOWN_PROVIDERS.get(provider, (provider or "").replace("_", " ").title())


def mcp_enabled() -> bool:
    """The master switch. Off by default — the whole action layer is dormant
    until MCP_ACTIONS_ENABLED is set in the environment."""
    return bool(get_settings().mcp_actions_enabled)


def _connections():
    return get_db()["client_connections"]


def ensure_connection_indexes() -> None:
    col = _connections()
    # One connection per (client, provider). Tenant-scoped uniqueness.
    col.create_index([("client_name", ASCENDING), ("provider", ASCENDING)], unique=True)


# ─── Write ──────────────────────────────────────────────────────────────────

def set_connection(
    client_name: str,
    provider: str,
    url: str,
    *,
    auth_type: str = "bearer",   # "bearer" | "none"
    token: Optional[str] = None,
    enabled: bool = True,
) -> dict:
    """Register (or update) a client's MCP server connection.

    A bearer token is encrypted at rest. If a token is supplied but no
    encryption key is configured, we RAISE rather than ever storing it in the
    clear — same rule as email credentials.
    """
    if not client_name or not provider or not url:
        raise ValueError("client_name, provider and url are required")

    set_fields: dict = {
        "client_name": client_name,
        "provider":    provider,
        "url":         url,
        "auth_type":   auth_type,
        "enabled":     bool(enabled),
        "updated_at":  datetime.now(timezone.utc),
    }

    if auth_type == "bearer" and token:
        if not crypto.available():
            raise RuntimeError(
                "EMAIL_CRED_KEY not configured — refusing to store an MCP token "
                "without encryption")
        enc = crypto.encrypt(token)
        if not enc:
            raise RuntimeError("MCP token encryption failed")
        set_fields["token_enc"] = enc
    elif auth_type == "none":
        # No-auth server — clear any stale token.
        set_fields["token_enc"] = None

    _connections().update_one(
        {"client_name": client_name, "provider": provider},
        {"$set": set_fields, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    log.info("mcp_connection_set", client=client_name, provider=provider,
             auth_type=auth_type, enabled=bool(enabled))  # never log url/token
    return public_view(get_connection(client_name, provider) or {})


def set_enabled(client_name: str, provider: str, enabled: bool) -> bool:
    res = _connections().update_one(
        {"client_name": client_name, "provider": provider},
        {"$set": {"enabled": bool(enabled), "updated_at": datetime.now(timezone.utc)}},
    )
    return bool(res.matched_count)


def delete_connection(client_name: str, provider: str) -> bool:
    res = _connections().delete_one({"client_name": client_name, "provider": provider})
    if res.deleted_count:
        log.info("mcp_connection_deleted", client=client_name, provider=provider)
    return bool(res.deleted_count)


# ─── Read ───────────────────────────────────────────────────────────────────

def get_connection(client_name: str, provider: str) -> Optional[dict]:
    """Raw connection doc (includes token_enc), scoped to this client. Case-
    insensitive on client_name so it matches the same way drafts are scoped."""
    if not client_name or not provider:
        return None
    return _connections().find_one({
        "client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"},
        "provider":    provider,
    })


def public_view(doc: dict) -> dict:
    """Connection without the secret — safe to return from the API / log."""
    if not doc:
        return {}
    return {
        "client_name": doc.get("client_name"),
        "provider":    doc.get("provider"),
        "label":       provider_label(doc.get("provider") or ""),
        "url":         doc.get("url"),
        "auth_type":   doc.get("auth_type"),
        "enabled":     bool(doc.get("enabled")),
        "has_token":   bool(doc.get("token_enc")),
        "created_at":  doc.get("created_at"),
        "updated_at":  doc.get("updated_at"),
    }


def list_connections(client_name: Optional[str] = None) -> list[dict]:
    """All connections (admin), or just one client's. Secrets stripped."""
    q: dict = {}
    if client_name:
        q["client_name"] = {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}
    return [public_view(d) for d in _connections().find(q).sort("provider", ASCENDING)]


def resolve_connection(client_name: str, provider: str) -> Optional[dict]:
    """Runtime connection (decrypted token) for the executor — ONLY if it exists
    and is enabled. Returns None otherwise. This is the only place a token is
    decrypted; callers must never log the result."""
    doc = get_connection(client_name, provider)
    if not doc or not doc.get("enabled"):
        return None
    token = None
    if doc.get("auth_type") == "bearer" and doc.get("token_enc"):
        token = crypto.decrypt(doc["token_enc"])
        if not token:
            log.warning("mcp_connection_token_decrypt_failed",
                        client=client_name, provider=provider)
            return None
    return {
        "client_name": doc.get("client_name"),
        "provider":    provider,
        "url":         doc.get("url"),
        "auth_type":   doc.get("auth_type") or "none",
        "token":       token,
    }
