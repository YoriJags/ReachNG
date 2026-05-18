"""
Email finder for SDR-discovered leads.

Google Maps returns name, phone, website — but never email. Apollo's free
tier doesn't expose emails either. So when our SDR funnel wants to send
an email outreach, we need to find one. This is where it happens.

Strategy (cheap → expensive):
  1. Regex sweep on the homepage HTML — catches obvious mailto: + plaintext
  2. Regex sweep on /contact, /about pages — most businesses list email here
  3. LeanScrape + Haiku extraction — semantic find on the contact page text,
     handles "reach us at hello [at] company [dot] com" obfuscation

Caches results in `leads.email_finder_cache` so we never re-scrape the same
domain. Honours robots.txt via leanscrape's fetcher.

NEVER guesses (no "info@{domain}" SMTP-probe — too noisy, hits spam traps).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import structlog
from pydantic import BaseModel

from database import get_db
from services.lean_scraper import _fetch as ls_fetch, scrape as ls_scrape

log = structlog.get_logger()


EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

# Skip emails that aren't real business contacts
BLOCKED_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "wordpress", "example", "test", "admin@admin",
    "youremail", "your-email", "name@example", "info@example",
    "user@example", "email@example",
}
BLOCKED_DOMAINS = {
    "example.com", "example.org", "domain.com", "sentry.io",
    "wordpress.com", "wpengine.com", "wixpress.com",
}


class _EmailHint(BaseModel):
    primary_email: Optional[str] = None
    role_emails: list[str] = []


# ─── Cache ────────────────────────────────────────────────────────────────

CACHE_TTL_DAYS = 30


def _cache_col():
    return get_db()["email_finder_cache"]


def _cached_lookup(domain: str) -> Optional[dict]:
    doc = _cache_col().find_one({"domain": domain})
    if not doc:
        return None
    age = datetime.now(timezone.utc) - doc.get("checked_at", datetime.now(timezone.utc))
    if age.days > CACHE_TTL_DAYS:
        return None
    return doc


def _cache_save(domain: str, email: Optional[str], source: str) -> None:
    _cache_col().update_one(
        {"domain": domain},
        {"$set": {
            "domain":     domain,
            "email":      email,
            "source":     source,
            "checked_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────

def _normalise_domain(url: str) -> Optional[str]:
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
        host = (p.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def _looks_real(email: str, domain_hint: Optional[str] = None) -> bool:
    e = email.strip().lower()
    if "@" not in e:
        return False
    local, _, host = e.partition("@")
    if not local or not host:
        return False
    if local in BLOCKED_LOCAL_PARTS or host in BLOCKED_DOMAINS:
        return False
    if any(local.startswith(b) for b in ("noreply", "no-reply", "donotreply")):
        return False
    if local.startswith("sentry"):
        return False
    # Heuristic: skip if email is from a wholly unrelated big-platform domain
    # unless it matches the business domain
    common_inboxes = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}
    if host in common_inboxes:
        # Personal inbox — still real but lower-confidence. Allow.
        return True
    return True


def _extract_from_html(html: str, domain_hint: Optional[str] = None) -> Optional[str]:
    """First-pass regex sweep. Prefer email that matches the business domain."""
    if not html:
        return None
    hits = list({h.lower() for h in EMAIL_RE.findall(html)})
    if not hits:
        return None
    real = [h for h in hits if _looks_real(h, domain_hint)]
    if not real:
        return None
    # Prefer email at the same domain
    if domain_hint:
        on_domain = [h for h in real if h.endswith("@" + domain_hint)]
        if on_domain:
            # Prefer role-named (info@, hello@, contact@) at the business domain
            for prefer in ("hello@", "info@", "contact@", "enquiries@", "bookings@", "sales@"):
                for e in on_domain:
                    if e.startswith(prefer):
                        return e
            return on_domain[0]
    # Otherwise return the first plausible
    return real[0]


async def _try_path(base_url: str, path: str, domain: Optional[str]) -> Optional[str]:
    try:
        url = urljoin(base_url, path)
        html = await ls_fetch(url)
        return _extract_from_html(html or "", domain)
    except Exception as e:
        log.debug("email_finder_path_failed", path=path, error=str(e))
        return None


# ─── Public ────────────────────────────────────────────────────────────────

async def find_email_for_business(website: Optional[str]) -> Optional[dict]:
    """Find a public email for a business given its website URL.

    Returns {"email": str, "source": str} on hit, None on miss.
    Source ∈ {"cache", "homepage_regex", "contact_page_regex", "haiku_extract"}.
    Cached for 30 days per domain.
    """
    if not website:
        return None
    domain = _normalise_domain(website)
    if not domain:
        return None

    # 1) Cache
    cached = _cached_lookup(domain)
    if cached:
        if cached.get("email"):
            log.info("email_finder_cache_hit", domain=domain, source="cache")
            return {"email": cached["email"], "source": "cache"}
        # Cached miss within TTL — don't re-scrape
        return None

    base = website if "://" in website else f"https://{website}"

    # 2) Homepage regex sweep
    email = await _try_path(base, "/", domain)
    if email:
        log.info("email_finder_homepage_hit", domain=domain)
        _cache_save(domain, email, "homepage_regex")
        return {"email": email, "source": "homepage_regex"}

    # 3) Common contact pages
    for path in ("/contact", "/contact-us", "/about", "/about-us", "/get-in-touch"):
        email = await _try_path(base, path, domain)
        if email:
            log.info("email_finder_contact_page_hit", domain=domain, path=path)
            _cache_save(domain, email, "contact_page_regex")
            return {"email": email, "source": "contact_page_regex"}

    # 4) Haiku semantic extract (handles obfuscated "name [at] domain [dot] com")
    try:
        for path in ("/contact", "/about", "/"):
            result = await ls_scrape(
                urljoin(base, path),
                _EmailHint,
                hint=(
                    "Find the primary business contact email. "
                    "Watch for obfuscation: 'hello [at] company [dot] com' = hello@company.com. "
                    "Prefer role-based (hello@, info@, contact@) on the business's own domain. "
                    "If you only see noreply/wordpress/example emails, return null."
                ),
            )
            if not result:
                continue
            primary = (result.get("primary_email") or "").strip().lower()
            if primary and _looks_real(primary, domain):
                log.info("email_finder_haiku_hit", domain=domain)
                _cache_save(domain, primary, "haiku_extract")
                return {"email": primary, "source": "haiku_extract"}
            for re_email in result.get("role_emails", []) or []:
                e = re_email.strip().lower()
                if e and _looks_real(e, domain):
                    _cache_save(domain, e, "haiku_extract")
                    return {"email": e, "source": "haiku_extract"}
    except Exception as e:
        log.warning("email_finder_haiku_failed", domain=domain, error=str(e))

    # Cache the miss so we don't burn cycles re-scraping
    _cache_save(domain, None, "miss")
    log.info("email_finder_no_email", domain=domain)
    return None


def ensure_email_finder_indexes() -> None:
    col = _cache_col()
    col.create_index([("domain", 1)], unique=True)
    col.create_index([("checked_at", 1)])
