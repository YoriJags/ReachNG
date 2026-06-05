"""Per-client feature flags for the EYO inventions.

The five inventions (Shield, Haggle, Radar, Cashflow, Referral) are each wired
into live paths NON-BLOCKING and gated behind one of these flags. Flags default
OFF — the founder enables each per client during onboarding once it has been
seen to behave. Nothing changes for an existing client until a flag is flipped.

Storage: client_doc["eyo"] = {"cashflow": True, "radar": True, ...}. A missing
"eyo" key (or a missing client) reads as all-off. Fail-safe: any DB error reads
as disabled, so a hiccup can never accidentally enable a feature or break the
caller that's checking.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()

# Canonical flag keys — kept in one place so the brief, the drafter, the webhook
# wiring, and the admin toggle never drift out of sync.
EYO_FEATURES = ("shield", "haggle", "radar", "cashflow", "referral")


def eyo_enabled(client_name: str, feature: str) -> bool:
    """True only if this client has explicitly enabled `feature`.

    Defaults OFF for unknown features, blank names, missing clients, and any
    read error. Never raises.
    """
    if feature not in EYO_FEATURES or not client_name:
        return False
    try:
        from database import get_db
        c = get_db()["clients"].find_one({"name": client_name}, {"eyo": 1})
        return bool(c and (c.get("eyo") or {}).get(feature) is True)
    except Exception as e:
        log.warning("eyo_flag_read_failed", feature=feature, error=str(e))
        return False


def eyo_flags_for(client_name: str) -> dict:
    """All five flags for a client as a plain dict (every key present, off by
    default). Convenient for the admin toggle UI and the portal. Fail-safe to
    all-off."""
    base = {f: False for f in EYO_FEATURES}
    if not client_name:
        return base
    try:
        from database import get_db
        c = get_db()["clients"].find_one({"name": client_name}, {"eyo": 1})
        stored = (c or {}).get("eyo") or {}
        for f in EYO_FEATURES:
            base[f] = stored.get(f) is True
    except Exception as e:
        log.warning("eyo_flags_read_failed", error=str(e))
    return base
