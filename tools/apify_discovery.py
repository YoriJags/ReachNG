"""
AI-powered lead discovery — finds B2B decision-makers by vertical + city.

Uses DuckDuckGo search (free, no API key) to find companies, then enriches
each domain with httpx + Claude Haiku for contacts.

No Apify, no ScrapeGraphAI, no paid services — just the Anthropic API we
already pay for and free DuckDuckGo search.
"""
import asyncio
from typing import Optional
from config import get_settings
import structlog

log = structlog.get_logger()


# ─── Search queries per vertical ─────────────────────────────────────────────

VERTICAL_QUERIES: dict[str, str] = {
    "real_estate": (
        "{city} Nigeria real estate agency luxury property developer estate agent site"
    ),
    "recruitment": (
        "{city} Nigeria recruitment agency HR consulting firm talent acquisition"
    ),
    "legal": (
        "{city} Nigeria law firm commercial legal practice solicitors"
    ),
    "events": (
        "{city} Nigeria corporate event management brand activation company"
    ),
    "fintech": (
        "{city} Nigeria fintech startup digital financial services company"
    ),
    "logistics": (
        "{city} Nigeria logistics haulage freight company"
    ),
    "insurance": (
        "{city} Nigeria insurance broker company"
    ),
    "agency_sales": (
        "{city} Nigeria digital marketing agency consulting firm professional services"
    ),
}


# ─── DuckDuckGo search ────────────────────────────────────────────────────────

def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    """Synchronous DuckDuckGo search — returns list of {title, href, body}."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results or []
    except Exception as e:
        log.error("ddg_search_failed", query=query[:80], error=str(e))
        return []


async def _ddg_search(query: str, max_results: int) -> list[dict]:
    """Async wrapper — runs DDG search in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ddg_search_sync, query, max_results)


# ─── Domain extraction ────────────────────────────────────────────────────────

def _extract_domain(url: str) -> Optional[str]:
    """Extract clean domain from URL, skipping aggregator sites."""
    _SKIP_DOMAINS = {
        "google.com", "bing.com", "facebook.com", "linkedin.com",
        "twitter.com", "youtube.com", "wikipedia.org", "instagram.com",
        "yellowpages.com.ng", "businesslist.com.ng", "nairaland.com",
        "vconnect.com", "ngcareers.com", "jobberman.com",
    }
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lstrip("www.")
        if not domain:
            return None
        root = ".".join(domain.split(".")[-2:])
        if root in _SKIP_DOMAINS or any(s in domain for s in _SKIP_DOMAINS):
            return None
        return domain
    except Exception:
        return None


def _result_to_lead_stub(result: dict, vertical: str, city: str) -> dict:
    """Convert a DDG result to a minimal lead dict for enrichment."""
    url = result.get("href", "")
    title = result.get("title", "")
    domain = _extract_domain(url)

    from urllib.parse import urlparse
    parsed_url = urlparse(url) if url else None
    website = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url and parsed_url.netloc else None

    name = title.split(" - ")[0].split(" | ")[0].strip() or domain or "Unknown"

    return {
        "place_id": f"ddg_{hash(url + city)}",
        "name": name,
        "vertical": vertical,
        "source": "ddg",
        "phone": None,
        "email": None,
        "address": city,
        "website": website,
        "domain": domain,
        "rating": None,
        "category": vertical.replace("_", " ").title(),
        "contact_name": None,
        "contact_title": None,
        "linkedin_url": None,
        "enrichment": None,
        "lead_temperature": 0,
        "temperature_reason": None,
    }


# ─── Public interface ─────────────────────────────────────────────────────────

async def discover_apify_leads(
    vertical: str,
    max_results: int = 20,
    city_override: Optional[str] = None,
) -> list[dict]:
    """
    Discover B2B leads via DuckDuckGo + httpx/Haiku enrichment.
    Returns lead dicts compatible with the leads Mongo schema.

    Falls back silently if ANTHROPIC_API_KEY is not set.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.warning("anthropic_key_missing", vertical=vertical)
        return []

    city = city_override or settings.default_city.split(",")[0].strip()
    query_template = VERTICAL_QUERIES.get(
        vertical,
        "{city} Nigeria {vertical} company business"
    )
    query = query_template.format(city=city, vertical=vertical.replace("_", " "))

    raw_results = await _ddg_search(query, max_results=min(max_results, 15))
    if not raw_results:
        log.info("ddg_no_results", vertical=vertical, city=city)
        return []

    # Deduplicate by domain
    seen_domains: set[str] = set()
    stubs: list[dict] = []
    for r in raw_results:
        stub = _result_to_lead_stub(r, vertical, city)
        if stub["domain"] and stub["domain"] not in seen_domains:
            seen_domains.add(stub["domain"])
            stubs.append(stub)

    if not stubs:
        return []

    # Enrich each domain with website scrape (httpx + Haiku)
    from tools.apify_enrich import enrich_lead
    sem = asyncio.Semaphore(4)

    async def _enrich_one(stub: dict) -> dict:
        if not stub.get("domain"):
            return stub
        async with sem:
            enrichment = await enrich_lead(domain=stub["domain"])
            if enrichment.get("email"):
                stub["email"] = enrichment["email"]
            if enrichment.get("phone"):
                stub["phone"] = enrichment["phone"]
            if enrichment.get("decision_maker"):
                stub["contact_name"] = enrichment["decision_maker"]
            stub["enrichment"] = enrichment
        return stub

    results = await asyncio.gather(*[_enrich_one(s) for s in stubs], return_exceptions=True)

    leads = []
    for item in results:
        if isinstance(item, Exception):
            log.warning("ddg_discovery_item_error", error=str(item))
            continue
        leads.append(item)

    log.info("ddg_discovery_complete", vertical=vertical, city=city, count=len(leads))
    return leads
