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
}

VERTICAL_KEYWORDS = {
    "real_estate": ["real estate", "property development", "estate management"],
    "recruitment": ["recruitment", "staffing", "talent acquisition", "HR consulting"],
    "events": ["event management", "event planning", "brand activation", "experiential"],
    "fintech": ["fintech", "digital lending", "microfinance", "payment solutions"],
    "legal": ["law firm", "legal services", "solicitors", "corporate law"],
    "logistics": ["haulage", "logistics", "freight forwarding", "last mile delivery"],
}


# ─── API calls ────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _people_search(
    titles: list[str],
    keywords: list[str],
    city: str,
    api_key: str,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Apollo people search — returns contacts with company info."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{APOLLO_BASE}/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": api_key,
            },
            json={
                "person_titles": titles,
                "q_keywords": " OR ".join(keywords),
                "person_locations": [city],
                "page": page,
                "per_page": per_page,
                "contact_email_status": ["verified", "guessed", "unverified"],
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
    seen_emails: set[str] = set()
    page = 1

    while len(results) < max_results:
        try:
            data = await _people_search(
                titles=titles,
                keywords=keywords,
                city=city,
                api_key=api_key,
                page=page,
                per_page=min(25, max_results - len(results)),
            )
        except Exception as e:
            log.error("apollo_search_failed", vertical=vertical, city=city, error=str(e))
            break

        people = data.get("people", []) or data.get("contacts", [])
        if not people:
            break  # No more results

        for person in people:
            if len(results) >= max_results:
                break

            email = person.get("email")
            phone = (
                person.get("phone_numbers", [{}])[0].get("sanitized_number")
                if person.get("phone_numbers")
                else None
            )

            # Need at least one contact method
            if not email and not phone:
                continue

            # Deduplicate by email
            if email and email in seen_emails:
                continue
            if email:
                seen_emails.add(email)

            company = person.get("organization") or {}
            name = company.get("name") or person.get("company_name") or ""
            if not name:
                continue

            results.append({
                "place_id": f"apollo_{person.get('id', '')}",
                "name": name,
                "vertical": vertical,
                "phone": _format_phone(phone),
                "email": email,
                "address": _build_address(person, company),
                "website": company.get("website_url"),
                "rating": None,  # Apollo has no rating
                "category": _vertical_to_category(vertical),
                "source": "apollo",
                "contact_name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                "contact_title": person.get("title"),
                "linkedin_url": person.get("linkedin_url"),
            })

        # Apollo pagination
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


def _build_address(person: dict, company: dict) -> Optional[str]:
    parts = []
    city = person.get("city") or company.get("city")
    country = person.get("country") or company.get("country")
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
    }
    return mapping.get(vertical, vertical.replace("_", " ").title())
