"""
Enrichment layer — given a company domain, extracts emails, phones, and
team member names by crawling the site with httpx + Claude Haiku.

Fully free — no Apify, no third-party scraping service.
"""
import asyncio
import json
import re
import httpx
from typing import Optional
from config import get_settings
import structlog

log = structlog.get_logger()

_CONTACT_PAGES = ["", "/contact", "/contact-us", "/about", "/about-us", "/team"]
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ReachNG/1.0; +https://reachng.ng)",
    "Accept": "text/html,application/xhtml+xml",
}


# ─── Web fetch ────────────────────────────────────────────────────────────────

async def _fetch_pages(base_url: str) -> str:
    """Fetch homepage + common contact/about pages, return combined visible text."""
    combined: list[str] = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_HEADERS) as client:
        for path in _CONTACT_PAGES:
            try:
                resp = await client.get(f"{base_url.rstrip('/')}{path}")
                if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    combined.append(text[:4000])
            except Exception:
                pass
    return "\n\n".join(combined)[:12000]


# ─── Haiku contact extractor ──────────────────────────────────────────────────

async def _scrape_contacts(domain: str) -> dict:
    """
    Fetch company website pages and extract contact info via Claude Haiku.
    Returns {emails: [...], phones: [...], team_names: [...]}
    """
    import anthropic
    settings = get_settings()

    base_url = domain if domain.startswith("http") else f"https://{domain}"
    page_text = await _fetch_pages(base_url)
    if not page_text.strip():
        return {}

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system="You extract structured contact information from website text. Return only valid JSON.",
            messages=[{
                "role": "user",
                "content": (
                    "From the following website text, extract contact info. "
                    "Return JSON with keys: emails (list), phones (list), team_names (list of person names found). "
                    "Only include real values — no placeholders or examples.\n\n"
                    f"{page_text}"
                ),
            }],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        return {
            "emails": [e for e in (data.get("emails") or []) if isinstance(e, str)][:5],
            "phones": [p for p in (data.get("phones") or []) if isinstance(p, str)][:3],
            "team_names": [n for n in (data.get("team_names") or []) if isinstance(n, str)][:5],
        }
    except Exception as e:
        log.error("contact_scrape_failed", domain=domain, error=str(e))
        return {}


# ─── Public interface ─────────────────────────────────────────────────────────

async def enrich_lead(
    *,
    domain: Optional[str] = None,
    linkedin_company_url: Optional[str] = None,  # kept for API compat; ignored (no Apify)
    company_name: Optional[str] = None,
) -> dict:
    """
    Enrich a lead from its website domain.
    Returns a dict for Mongo upsert into lead['enrichment'].
    Never raises — returns partial result on failure.
    """
    from datetime import datetime, timezone

    result: dict = {
        "decision_maker": None,
        "title": None,
        "linkedin_url": None,
        "email": None,
        "phone": None,
        "recent_signal": None,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "source": [],
    }

    if not domain:
        return result

    try:
        contacts = await _scrape_contacts(domain)
    except Exception as e:
        log.warning("enrich_lead_failed", domain=domain, error=str(e))
        return result

    emails = contacts.get("emails", [])
    phones = contacts.get("phones", [])
    team_names = contacts.get("team_names", [])

    if emails:
        result["email"] = emails[0]
        result["source"].append("website")
    if phones:
        result["phone"] = phones[0]
    if team_names:
        result["decision_maker"] = team_names[0]
        result["recent_signal"] = f"Team members on site: {', '.join(team_names[:3])}"

    log.info("enrich_lead_complete", domain=domain, sources=result["source"])
    return result
