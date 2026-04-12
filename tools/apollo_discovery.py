"""
Apollo.io contact discovery — finds B2B decision-makers by vertical + city.
Runs in parallel with Google Maps and social discovery in BaseCampaign.run().
Docs: https://apolloio.github.io/apollo-api-docs/
"""
import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings
import structlog

log = structlog.get_logger()

APOLLO_BASE = "https://api.apollo.io/v1"

# ─── Vertical → Apollo title/keyword mapping ──────────────────────────────────

VERTICAL_TITLES = {
    "real_estate": [
        "Real Estate Agent", "Property Developer", "Estate Manager",
        "Head of Sales", "Director of Real Estate", "Property Consultant",
    ],
    "recruitment": [
        "Recruitment Manager", "Head of Talent", "HR Director",
        "Talent Acquisition", "Staffing Manager", "People Operations",
    ],
    "events": [
        "Event Manager", "Event Director", "Head of Events",
        "Brand Experience Manager", "Marketing Manager", "Creative Director",
    ],
    "fintech": [
        "CEO", "Founder", "Head of Business Development",
        "Chief Commercial Officer", "Head of Partnerships", "Product Director",
    ],
    "legal": [
        "Managing Partner", "Senior Partner", "Commercial Lawyer",
        "Head of Legal", "Corporate Counsel", "Legal Director",
    ],
    "logistics": [
        "Operations Director", "Fleet Manager", "Head of Logistics",
        "Supply Chain Manager", "Freight Manager", "Chief Operations Officer",
    ],
    "agriculture": [
        "CEO", "Founder", "Head of Agribusiness",
        "Farm Manager", "Agro Processing Director", "Head of Supply Chain",
    ],
}

VERTICAL_KEYWORDS = {
    "real_estate": ["real estate", "property development", "estate management"],
    "recruitment": ["recruitment", "staffing", "talent acquisition", "HR consulting"],
    "events": ["event management", "event planning", "brand activation", "experiential"],
    "fintech": ["fintech", "digital lending", "microfinance", "payment solutions"],
    "legal": ["law firm", "legal services", "solicitors", "corporate law"],
    "logistics": ["haulage", "logistics", "freight forwarding", "last mile delivery"],
    "agriculture": ["agribusiness", "farm produce", "food processing", "agricultural cooperative", "poultry", "aquaculture"],
    "agency_sales": ["real estate agency", "recruitment agency", "law firm", "event management", "insurance broker", "digital marketing agency", "consulting firm", "training company"],
}


# ─── API calls ────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _org_search(
    keywords: list[str],
    city: str,
    api_key: str,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Apollo organization search — available on free plan."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{APOLLO_BASE}/mixed_companies/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": api_key,
            },
            json={
                "q_keywords": " OR ".join(keywords),
                "organization_locations": [city],
                "page": page,
                "per_page": per_page,
            },
        )
        resp.raise_for_status()
        return resp.json()


# ─── Public interface ─────────────────────────────────────────────────────────

async def discover_apollo_leads(
    vertical: str,
    max_results: int = 30,
    city_override: Optional[str] = None,
) -> list[dict]:
    """
    Search Apollo for B2B decision-makers in a vertical + city.
    Returns list of enriched contact dicts in the same format as discover_businesses().
    Falls back silently if API key not set.
    """
    settings = get_settings()
    api_key = settings.apollo_api_key
    if not api_key:
        log.warning("apollo_key_missing", vertical=vertical)
        return []

    city = city_override or settings.default_city
    titles = VERTICAL_TITLES.get(vertical, ["CEO", "Founder", "Managing Director"])
    keywords = VERTICAL_KEYWORDS.get(vertical, [vertical])

    results: list[dict] = []
    seen_domains: set[str] = set()
    page = 1

    while len(results) < max_results:
        try:
            data = await _org_search(
                keywords=keywords,
                city=city,
                api_key=api_key,
                page=page,
                per_page=min(25, max_results - len(results)),
            )
        except Exception as e:
            log.error("apollo_search_failed", vertical=vertical, city=city, error=str(e))
            break

        orgs = data.get("organizations", []) or data.get("accounts", [])
        if not orgs:
            break

        for org in orgs:
            if len(results) >= max_results:
                break

            name = org.get("name") or ""
            if not name:
                continue

            website = org.get("website_url") or org.get("primary_domain")
            phone = org.get("sanitized_phone") or org.get("phone")
            domain = org.get("primary_domain")

            # Deduplicate by domain
            if domain and domain in seen_domains:
                continue
            if domain:
                seen_domains.add(domain)

            results.append({
                "place_id": f"apollo_{org.get('id', '')}",
                "name": name,
                "vertical": vertical,
                "phone": _format_phone(phone),
                "email": None,  # Org search doesn't return emails
                "address": _build_org_address(org),
                "website": website,
                "rating": None,
                "category": _vertical_to_category(vertical),
                "source": "apollo",
                "contact_name": None,
                "contact_title": None,
                "linkedin_url": org.get("linkedin_url"),
            })

        pagination = data.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    log.info("apollo_discovery_complete", vertical=vertical, city=city, count=len(results))
    return results


def _format_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = "+234" + cleaned[1:]
    return cleaned


def _build_org_address(org: dict) -> Optional[str]:
    parts = []
    city = org.get("city")
    country = org.get("country")
    if city:
        parts.append(city)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else None


def _vertical_to_category(vertical: str) -> str:
    mapping = {
        "real_estate": "Real Estate",
        "recruitment": "Staffing Agency",
        "events": "Event Management",
        "fintech": "Financial Technology",
        "legal": "Law Firm",
        "logistics": "Logistics",
        "agriculture": "Agriculture",
    }
    return mapping.get(vertical, vertical.replace("_", " ").title())
