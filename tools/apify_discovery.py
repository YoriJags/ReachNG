"""
AI-powered lead discovery — finds B2B decision-makers by vertical + city.

Uses ScrapeGraphAI SearchGraph (Anthropic/Haiku backend) to search Google,
crawl the top results, and extract structured company data in one pass.
No Apify Google Search actor needed — free, no per-run cost.

LinkedIn employee enrichment still uses Apify (residential proxy required).
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from config import get_settings
import structlog

log = structlog.get_logger()


# ─── Output schema ────────────────────────────────────────────────────────────

class CompanyContact(BaseModel):
    name: str = Field(description="Company or agency name")
    website: Optional[str] = Field(default=None, description="Company website URL")
    email: Optional[str] = Field(default=None, description="Contact email address")
    phone: Optional[str] = Field(default=None, description="Contact phone number")
    decision_maker: Optional[str] = Field(default=None, description="Name of founder, MD, CEO or director")
    title: Optional[str] = Field(default=None, description="Title of the decision maker")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn company or profile URL")


class CompanyList(BaseModel):
    companies: list[CompanyContact] = Field(description="List of companies found")


# ─── Vertical search prompts ──────────────────────────────────────────────────

VERTICAL_PROMPTS: dict[str, str] = {
    "real_estate": (
        "Find real estate agencies and property development companies in {city}, Nigeria. "
        "For each company extract: company name, website, email, phone number, and the name "
        "and title of the founder, MD, CEO or director. Focus on luxury and mid-market firms."
    ),
    "recruitment": (
        "Find recruitment agencies and HR consulting firms in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the founder or MD name and title."
    ),
    "legal": (
        "Find law firms and commercial legal practices in {city}, Nigeria. "
        "For each extract: firm name, website, email, phone, and the managing partner or senior partner name."
    ),
    "events": (
        "Find corporate event management and brand activation companies in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the CEO or director name and title."
    ),
    "fintech": (
        "Find fintech startups and digital financial services companies in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the founder or CEO name."
    ),
    "logistics": (
        "Find logistics, haulage and freight companies in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the operations director or MD name."
    ),
    "insurance": (
        "Find insurance brokers and insurance companies in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the director or MD name."
    ),
    "agency_sales": (
        "Find consulting firms, digital marketing agencies, and professional service firms in {city}, Nigeria. "
        "For each extract: company name, website, email, phone, and the founder or managing partner name."
    ),
}


# ─── SearchGraph runner ───────────────────────────────────────────────────────

def _run_search_graph_sync(prompt: str, api_key: str, max_results: int) -> list[CompanyContact]:
    """
    Synchronous SearchGraph run — called via executor to stay async-compatible.
    Returns list of CompanyContact parsed by the schema.
    """
    from scrapegraphai.graphs import SearchGraph

    config = {
        "llm": {
            "api_key": api_key,
            "model": "anthropic/claude-haiku-4-5-20251001",
        },
        "max_results": min(max_results, 10),
        "verbose": False,
        "headless": True,
    }

    graph = SearchGraph(prompt=prompt, config=config, schema=CompanyList)
    result = graph.run()

    # result is either a CompanyList instance or a dict
    if isinstance(result, CompanyList):
        return result.companies
    if isinstance(result, dict):
        items = result.get("companies", [])
        return [CompanyContact(**i) if isinstance(i, dict) else i for i in items]
    return []


async def _run_search_graph(prompt: str, api_key: str, max_results: int) -> list[CompanyContact]:
    """Async wrapper — runs SearchGraph in thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None,
            _run_search_graph_sync,
            prompt,
            api_key,
            max_results,
        )
    except Exception as e:
        log.error("search_graph_failed", error=str(e))
        return []


# ─── Public interface ─────────────────────────────────────────────────────────

async def discover_apify_leads(
    vertical: str,
    max_results: int = 20,
    city_override: Optional[str] = None,
) -> list[dict]:
    """
    Discover B2B leads via ScrapeGraphAI SearchGraph + optional LinkedIn enrichment.
    Returns lead dicts compatible with the leads Mongo schema.

    Falls back silently if ANTHROPIC_API_KEY is not set.
    LinkedIn enrichment runs in parallel if APIFY_API_TOKEN is set.
    """
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if not api_key:
        log.warning("anthropic_key_missing", vertical=vertical)
        return []

    city = city_override or settings.default_city.split(",")[0].strip()
    prompt_template = VERTICAL_PROMPTS.get(
        vertical,
        "Find {vertical} companies in {city}, Nigeria with contact details and decision-maker names."
    )
    prompt = prompt_template.format(city=city, vertical=vertical.replace("_", " "))

    companies = await _run_search_graph(prompt, api_key, max_results)
    if not companies:
        log.info("search_graph_no_results", vertical=vertical, city=city)
        return []

    # Enrich with website scrape (httpx + Haiku) for any leads that have a domain
    from tools.apify_enrich import enrich_lead
    sem = asyncio.Semaphore(5)

    async def _enrich_one(c: CompanyContact) -> dict:
        base = _company_to_lead(c, vertical, city)
        if base.get("domain") and not base.get("email") and not base.get("contact_name"):
            async with sem:
                enrichment = await enrich_lead(domain=base["domain"])
                if enrichment.get("email"):
                    base["email"] = enrichment["email"]
                if enrichment.get("phone") and not base.get("phone"):
                    base["phone"] = enrichment["phone"]
                if enrichment.get("decision_maker") and not base["contact_name"]:
                    base["contact_name"] = enrichment["decision_maker"]
                base["enrichment"] = enrichment
        return base

    results = await asyncio.gather(*[_enrich_one(c) for c in companies], return_exceptions=True)

    leads = []
    for item in results:
        if isinstance(item, Exception):
            log.warning("apify_discovery_item_error", error=str(item))
            continue
        leads.append(item)

    log.info("apify_discovery_complete", vertical=vertical, city=city, count=len(leads))
    return leads


def _company_to_lead(c: CompanyContact, vertical: str, city: str) -> dict:
    """Convert a CompanyContact schema object to a leads Mongo dict."""
    from urllib.parse import urlparse
    domain = None
    if c.website:
        try:
            parsed = urlparse(c.website)
            domain = parsed.netloc.lstrip("www.") or None
        except Exception:
            pass

    return {
        "place_id": f"sgai_{hash(c.name + city)}",
        "name": c.name,
        "vertical": vertical,
        "source": "scrapegraph",
        "phone": c.phone,
        "email": c.email,
        "address": city,
        "website": c.website,
        "domain": domain,
        "rating": None,
        "category": vertical.replace("_", " ").title(),
        "contact_name": c.decision_maker,
        "contact_title": c.title,
        "linkedin_url": c.linkedin_url,
        "enrichment": None,
        "lead_temperature": 0,
        "temperature_reason": None,
    }
