"""
Business discovery via Google Maps Places API.
Finds Lagos businesses per vertical, extracts contact info.
"""
import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings
import structlog

log = structlog.get_logger()

PLACES_BASE = "https://maps.googleapis.com/maps/api/place"

# ─── Nearby city expansion map ────────────────────────────────────────────────
# When local pool runs thin, campaigns auto-expand to these cities.
# Ordered by proximity / business density.
NEARBY_CITIES: dict[str, list[str]] = {
    "Lagos":          ["Abuja", "Port Harcourt", "Ibadan", "Benin City"],
    "Abuja":          ["Lagos", "Kaduna", "Kano", "Jos"],
    "Port Harcourt":  ["Lagos", "Warri", "Calabar", "Uyo"],
    "Ibadan":         ["Lagos", "Abeokuta", "Osogbo", "Ilorin"],
    "Kano":           ["Kaduna", "Abuja", "Zaria", "Katsina"],
    "Benin City":     ["Lagos", "Warri", "Asaba", "Port Harcourt"],
    "Kaduna":         ["Abuja", "Kano", "Zaria", "Jos"],
    "Enugu":          ["Onitsha", "Owerri", "Abuja", "Port Harcourt"],
    "Onitsha":        ["Enugu", "Asaba", "Owerri", "Lagos"],
    "Warri":          ["Benin City", "Port Harcourt", "Asaba", "Lagos"],
    "Calabar":        ["Port Harcourt", "Uyo", "Enugu", "Lagos"],
    "Uyo":            ["Calabar", "Port Harcourt", "Lagos"],
    "Owerri":         ["Enugu", "Port Harcourt", "Onitsha", "Lagos"],
    "Abeokuta":       ["Lagos", "Ibadan", "Ilorin"],
    "Ilorin":         ["Ibadan", "Lagos", "Abuja", "Osogbo"],
    "Jos":            ["Abuja", "Kaduna", "Bauchi"],
    "London, UK":     ["Birmingham, UK", "Manchester, UK", "Bristol, UK"],
    "Nairobi":        ["Mombasa", "Kampala", "Dar es Salaam"],
    "Accra":          ["Kumasi", "Lagos", "Abidjan"],
    "Dubai":          ["Abu Dhabi", "Sharjah"],
}


def get_expansion_cities(primary_city: str, max_expansions: int = 2) -> list[str]:
    """Return nearby cities to expand into when the local pool runs thin."""
    for key, neighbours in NEARBY_CITIES.items():
        if key.lower() in primary_city.lower() or primary_city.lower() in key.lower():
            return neighbours[:max_expansions]
    return []

# ─── Vertical search configs ──────────────────────────────────────────────────

# Queries use {city} placeholder — substituted at runtime with client city (default: Lagos)
#
# VERTICAL_QUERIES  — ReachNG self-promotion: find businesses to pitch our products TO
# PROSPECT_QUERIES  — Client campaign mode: find that client's TARGET CUSTOMERS
#                     (their buyers/patients/tenants, not other businesses in their sector)
PROSPECT_QUERIES: dict[str, list[str]] = {
    "real_estate": [
        "property buyers {city}",
        "people looking for apartments {city}",
        "buy land {city}",
        "residential investors {city}",
        "house rental {city}",
    ],
    "recruitment": [
        "companies hiring {city}",
        "startups hiring {city}",
        "SME looking for staff {city}",
        "employers {city}",
        "companies expanding team {city}",
    ],
    "fintech": [
        "SME needing loans {city}",
        "small business owners {city}",
        "entrepreneurs seeking finance {city}",
        "businesses needing working capital {city}",
    ],
    "legal": [
        "startups needing legal services {city}",
        "SME needing contract review {city}",
        "companies CAC registration {city}",
        "businesses legal advice {city}",
    ],
    "logistics": [
        "ecommerce companies {city}",
        "manufacturers needing delivery {city}",
        "importers {city}",
        "online stores {city}",
    ],
    "agriculture": [
        "food processors {city}",
        "supermarkets {city}",
        "restaurant chains {city}",
        "hotels food supply {city}",
    ],
    "events": [
        "wedding planners {city}",
        "corporates planning events {city}",
        "party organisers {city}",
        "conference organisers {city}",
    ],
    "agency_sales": [
        "real estate agency {city}",
        "recruitment agency {city}",
        "law firm {city}",
        "event management company {city}",
        "consulting firm {city}",
        "digital marketing agency {city}",
        "logistics company {city}",
        "accounting firm {city}",
    ],
}

VERTICAL_QUERIES = {
    "real_estate": [
        "real estate agent {city}",
        "property developer {city}",
        "estate agent {city}",
        "real estate company {city}",
        "property sales {city}",
        "luxury apartments developer {city}",
        "housing developer {city}",
        "new property development {city}",
    ],
    "recruitment": [
        "recruitment agency {city}",
        "HR consulting firm {city}",
        "staffing agency {city}",
        "executive search firm {city}",
        "talent acquisition company {city}",
        "human resources outsourcing {city}",
    ],
    "events": [
        "event planner {city}",
        "event management company {city}",
        "event promoter {city}",
        "wedding planner {city}",
        "corporate event organizer {city}",
        "nightclub {city}",
        "lounge bar {city}",
        "event venue {city}",
    ],
    "fintech": [
        "microfinance bank {city}",
        "digital lending company {city}",
        "fintech company {city}",
        "credit company {city}",
        "loan company {city}",
        "financial technology firm {city}",
        "investment company {city}",
        "fintech startup {city}",
    ],
    "legal": [
        "law firm {city}",
        "commercial law firm {city}",
        "corporate law firm {city}",
        "legal services company {city}",
        "law chambers {city}",
        "solicitors and advocates {city}",
        "real estate law firm {city}",
        "intellectual property law firm {city}",
    ],
    "logistics": [
        "haulage company {city}",
        "logistics company {city}",
        "freight company {city}",
        "trucking company {city}",
        "last mile delivery company {city}",
        "cargo company {city}",
        "supply chain company {city}",
        "courier company {city}",
    ],
    "agriculture": [
        "agribusiness company {city}",
        "farm produce supplier {city}",
        "food processing company {city}",
        "agricultural cooperative {city}",
        "poultry farm {city}",
        "fish farm {city}",
        "crop farming company {city}",
        "agro allied company {city}",
    ],
    "agency_sales": [
        "real estate agency {city}",
        "recruitment agency {city}",
        "law firm {city}",
        "event management company {city}",
        "insurance broker {city}",
        "digital marketing agency {city}",
        "training company {city}",
        "consulting firm {city}",
        "logistics company {city}",
        "accounting firm {city}",
    ],
}

# Sector-level query groups within agency_sales — used for targeted outreach
AGENCY_SALES_SECTORS = {
    "real_estate":  ["real estate agency {city}", "property developer {city}", "estate management company {city}"],
    "recruitment":  ["recruitment agency {city}", "staffing agency {city}", "HR consulting firm {city}"],
    "legal":        ["law firm {city}", "legal services {city}", "solicitors {city}"],
    "events":       ["event management company {city}", "event planning company {city}", "corporate events {city}"],
    "insurance":    ["insurance broker {city}", "insurance company {city}", "insurance agent {city}"],
    "marketing":    ["digital marketing agency {city}", "advertising agency {city}", "PR agency {city}"],
    "training":     ["training company {city}", "professional development {city}", "corporate training {city}"],
    "consulting":   ["consulting firm {city}", "management consulting {city}", "business advisory {city}"],
    "logistics":    ["logistics company {city}", "freight company {city}", "courier service {city}"],
    "accounting":   ["accounting firm {city}", "audit firm {city}", "tax advisory {city}"],
}


# ─── API calls ────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _text_search(query: str, api_key: str) -> list[dict]:
    """Run a Places Text Search and return raw results."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PLACES_BASE}/textsearch/json",
            params={
                "query": query,
                "key": api_key,
                "region": "ng",
                "language": "en",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "UNKNOWN")
        if status not in ("OK", "ZERO_RESULTS"):
            log.warning("places_api_status", query=query, status=status,
                        error_message=data.get("error_message", ""))
        return data.get("results", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _place_details(place_id: str, api_key: str) -> dict:
    """Fetch full Place Details including phone and website."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PLACES_BASE}/details/json",
            params={
                "place_id": place_id,
                "fields": "name,formatted_phone_number,international_phone_number,website,formatted_address,rating,user_ratings_total,business_status",
                "key": api_key,
            },
        )
        resp.raise_for_status()
        return resp.json().get("result", {})


# ─── Public interface ─────────────────────────────────────────────────────────

async def discover_businesses(
    vertical: str,
    max_results: int = 60,
    query_override: Optional[str] = None,
    city_override: Optional[str] = None,
    target_sectors: Optional[list[str]] = None,
    is_client_campaign: bool = False,
) -> list[dict]:
    """
    Discover businesses for a vertical.
    city_override: replaces "Lagos" in all queries — e.g. "London, UK" for international clients.
    is_client_campaign: when True, uses PROSPECT_QUERIES to find the client's target customers
                        rather than VERTICAL_QUERIES which finds businesses to pitch ReachNG to.
    Returns a list of enriched contact dicts ready for upsert.
    """
    settings = get_settings()
    api_key = settings.google_maps_api_key
    city = city_override or settings.default_city.split(",")[0].strip()  # e.g. "Lagos"

    if query_override:
        queries = [query_override]
    elif is_client_campaign and vertical in PROSPECT_QUERIES:
        base_queries = PROSPECT_QUERIES[vertical]
        queries = [q.format(city=city) for q in base_queries]
    elif vertical == "agency_sales" and target_sectors:
        # Build queries from only the requested sectors
        raw_queries = []
        for sector in target_sectors:
            raw_queries.extend(AGENCY_SALES_SECTORS.get(sector, []))
        queries = [q.format(city=city) for q in raw_queries] if raw_queries else \
                  [q.format(city=city) for q in VERTICAL_QUERIES.get(vertical, [])]
    else:
        base_queries = VERTICAL_QUERIES.get(vertical, [])
        queries = [q.format(city=city) for q in base_queries]
    seen_place_ids: set[str] = set()
    results: list[dict] = []

    for query in queries:
        if len(results) >= max_results:
            break

        try:
            raw = await _text_search(query, api_key)
        except Exception as e:
            log.error("places_search_failed", query=query, error=str(e))
            continue

        for place in raw:
            if len(results) >= max_results:
                break

            place_id = place.get("place_id")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            # Only open/operational businesses
            if place.get("business_status") not in (None, "OPERATIONAL"):
                continue

            try:
                details = await _place_details(place_id, api_key)
            except Exception as e:
                log.warning("place_details_failed", place_id=place_id, error=str(e))
                details = {}

            phone = (
                details.get("international_phone_number")
                or details.get("formatted_phone_number")
            )
            # Skip contacts with no phone AND no website — can't reach them
            if not phone and not details.get("website"):
                continue

            # Temperature signal: few total ratings → recently listed → warm lead
            user_ratings = details.get("user_ratings_total") or place.get("user_ratings_total") or 0
            temp, temp_reason = 0, None
            if user_ratings < 10:
                temp, temp_reason = 1, "recently_listed_on_maps"

            results.append({
                "place_id": place_id,
                "name": place.get("name", ""),
                "vertical": vertical,
                "source": "maps",
                "phone": _normalise_phone(phone),
                "website": details.get("website"),
                "address": details.get("formatted_address") or place.get("formatted_address"),
                "rating": details.get("rating") or place.get("rating"),
                "category": _extract_category(place),
                "lead_temperature": temp,
                "temperature_reason": temp_reason,
            })

    log.info("discovery_complete", vertical=vertical, count=len(results))
    return results


def _normalise_phone(phone: Optional[str]) -> Optional[str]:
    """Strip spaces/dashes, ensure +234 format for Nigerian numbers."""
    if not phone:
        return None
    cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    # Convert local 0XX to international +234XX
    if cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = "+234" + cleaned[1:]
    return cleaned


def _extract_category(place: dict) -> Optional[str]:
    types = place.get("types", [])
    # Return the first non-generic type
    skip = {"point_of_interest", "establishment", "premise", "political", "locality"}
    for t in types:
        if t not in skip:
            return t.replace("_", " ").title()
    return None
