"""
Outreach short-link service — turns ugly UTM-tagged URLs into clean
'www.reachng.ng/o/abc123' redirectors.

Each minted link maps to a target URL stored in Mongo. When a recipient
taps the short link, the route handler issues a 302 to the real URL
(still carrying utm_source / utm_medium / utm_campaign / v / c so PostHog
attribution works) and bumps a click counter.

Why: the founder voice cold-outreach emails were ending with a wall of
UTM querystring noise that flagged 'marketing email' on first scan and
killed the credibility of an otherwise-clean introduction. Short links
let us keep attribution without the noise.

Schema (collection: outreach_links):
    { slug, target_url, vertical, contact_id, variant, created_at,
      first_click_at, last_click_at, clicks }
    Index: slug unique. (vertical, contact_id, variant) for upserts.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

import structlog
from pymongo import ASCENDING

from database import get_db

log = structlog.get_logger()


SLUG_BYTES = 6           # ~8 base32 chars — short, readable, ~2^48 namespace
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/O/1/I/L confusion


def _col():
    return get_db()["outreach_links"]


def ensure_outreach_link_indexes() -> None:
    _col().create_index([("slug", ASCENDING)], unique=True)
    _col().create_index([("vertical", ASCENDING), ("contact_id", ASCENDING),
                          ("variant", ASCENDING)])


def _new_slug() -> str:
    raw = secrets.token_bytes(SLUG_BYTES)
    # Convert random bytes to ALPHABET-only string for clean URLs
    n = int.from_bytes(raw, "big")
    out: list[str] = []
    base = len(ALPHABET)
    while n > 0:
        out.append(ALPHABET[n % base])
        n //= base
    return ("".join(reversed(out)) or "a").ljust(8, "a")[:10]


def mint(
    *,
    target_url: str,
    vertical: Optional[str] = None,
    contact_id: Optional[str] = None,
    variant: str = "site",
) -> str:
    """Returns a slug. Idempotent on (vertical, contact_id, variant) — the
    same prospect always gets the same slug for the same link variant, so
    a second call doesn't pollute the table with duplicates."""
    if not target_url:
        raise ValueError("target_url required")

    if vertical and contact_id:
        existing = _col().find_one({
            "vertical":    vertical,
            "contact_id":  str(contact_id),
            "variant":     variant,
        }, {"slug": 1, "target_url": 1})
        if existing:
            # If the target URL changed (eg utm params shifted), update it
            if existing.get("target_url") != target_url:
                _col().update_one({"_id": existing["_id"]},
                                   {"$set": {"target_url": target_url}})
            return existing["slug"]

    # Mint a fresh slug, retry on collision
    for _ in range(5):
        slug = _new_slug()
        try:
            _col().insert_one({
                "slug":         slug,
                "target_url":   target_url,
                "vertical":     vertical,
                "contact_id":   str(contact_id) if contact_id else None,
                "variant":      variant,
                "created_at":   datetime.now(timezone.utc),
                "first_click_at": None,
                "last_click_at":  None,
                "clicks":       0,
            })
            return slug
        except Exception:
            continue  # slug collision — try another
    raise RuntimeError("could not mint a unique slug after 5 attempts")


def resolve(slug: str) -> Optional[str]:
    """Returns the target URL for a slug, or None. Side-effect: bumps clicks."""
    if not slug:
        return None
    doc = _col().find_one_and_update(
        {"slug": slug},
        {"$inc": {"clicks": 1},
         "$set": {"last_click_at": datetime.now(timezone.utc)},
         "$min": {"first_click_at": datetime.now(timezone.utc)}},
        return_document=False,
    )
    return (doc or {}).get("target_url")
