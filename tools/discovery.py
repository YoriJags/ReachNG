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

# ─── Vertical search configs ──────────────────────────────────────────────────

VERTICAL_QUERIES = {
    "real_estate": [
        "real estate agent Lagos",
        "property developer Lagos",
        "estate agent Victoria Island Lagos",
        "property developer Lekki Lagos",
        "real estate company Ikoyi Lagos",
        "property sales Lagos Island",
        "luxury apartments developer Lagos",
        "new development Ajah Lagos",
    ],
    "recruitment": [
        "recruitment agency Lagos",
        "HR consulting firm Lagos",
        "staffing agency Victoria Island Lagos",
        "executive search firm Lagos",
        "talent acquisition company Lagos",
        "human resources outsourcing Lagos",
    ],
    "events": [
        "event planner Lagos",
        "event management company Lagos",
        "event promoter Lagos Island",
        "wedding planner Lagos",
        "corporate event organizer Lagos",
        "nightclub Victoria Island Lagos",
        "lounge bar Lekki Lagos",
        "event venue Lagos",
    ],
    "fintech": [
        "microfinance bank Lagos",
        "digital lending company Lagos",
        "fintech company Victoria Island Lagos",
        "credit company Lagos",
        "loan company Lekki Lagos",
        "financial technology firm Lagos",
        "investment company Ikoyi Lagos",
        "fintech startup Lagos Island",
    ],
    "legal": [
        "law firm Victoria Island Lagos",
        "commercial law firm Lagos",
        "corporate law firm Ikoyi Lagos",
        "legal services company Lagos",
        "law chambers Lagos Island",
        "solicitors and advocates Lagos",
        "real estate law firm Lagos",
        "intellectual property law firm Lagos",
    ],
    "logistics": [
        "haulage company Lagos",
        "logistics company Apapa Lagos",
        "freight company Lagos",
        "trucking company Lagos",
        "last mile delivery company Lagos",
        "logistics firm Ikorodu Lagos",
        "haulage firm Mile 2 Lagos",
        "cargo company Tin Can Lagos",
    ],
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
) -> list[dict]:
    """
    Discover businesses for a vertical.
    Returns a list of enriched contact dicts ready for upsert.
    """
    settings = get_settings()
    api_key = settings.google_maps_api_key

    queries = [query_override] if query_override else VERTICAL_QUERIES.get(vertical, [])
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

            results.append({
                "place_id": place_id,
                "name": place.get("name", ""),
                "vertical": vertical,
                "phone": _normalise_phone(phone),
                "website": details.get("website"),
                "address": details.get("formatted_address") or place.get("formatted_address"),
                "rating": details.get("rating") or place.get("rating"),
                "category": _extract_category(place),
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
