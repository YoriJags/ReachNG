"""
Competitor monitoring — discovers competing outreach/marketing agencies
operating in the same verticals. Tracks their positioning.
"""
import httpx
from datetime import datetime, timezone
from database import get_db
from config import get_settings
from pymongo import ASCENDING, DESCENDING
import structlog

log = structlog.get_logger()

PLACES_BASE = "https://maps.googleapis.com/maps/api/place"

COMPETITOR_QUERIES = [
    "digital marketing agency Lagos",
    "lead generation company Lagos",
    "outreach agency Victoria Island Lagos",
    "sales outsourcing Lagos",
    "B2B marketing firm Lagos",
    "cold calling agency Lagos",
    "marketing automation company Lagos",
]


def get_competitor_collection():
    return get_db()["competitors"]


def ensure_competitor_indexes():
    col = get_competitor_collection()
    col.create_index([("place_id", ASCENDING)], unique=True)
    col.create_index([("discovered_at", DESCENDING)])


async def discover_competitors(max_results: int = 30) -> list[dict]:
    """
    Find competing agencies via Google Maps.
    Stores them in MongoDB for ongoing monitoring.
    """
    settings = get_settings()
    api_key = settings.google_maps_api_key
    col = get_competitor_collection()
    seen: set[str] = set()
    added = []

    for query in COMPETITOR_QUERIES:
        if len(added) >= max_results:
            break
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{PLACES_BASE}/textsearch/json",
                    params={"query": query, "key": api_key, "region": "ng", "language": "en"},
                )
                resp.raise_for_status()
                places = resp.json().get("results", [])
        except Exception as e:
            log.error("competitor_search_failed", query=query, error=str(e))
            continue

        for place in places:
            if len(added) >= max_results:
                break
            place_id = place.get("place_id")
            if not place_id or place_id in seen:
                continue
            seen.add(place_id)

            doc = {
                "place_id": place_id,
                "name": place.get("name", ""),
                "address": place.get("formatted_address", ""),
                "rating": place.get("rating"),
                "discovered_at": datetime.now(timezone.utc),
                "query": query,
            }
            col.update_one(
                {"place_id": place_id},
                {"$set": doc},
                upsert=True,
            )
            added.append(doc)

    log.info("competitor_discovery_complete", count=len(added))
    return added


def list_competitors() -> list[dict]:
    docs = list(get_competitor_collection().find({}).sort("rating", -1))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


def get_competitor_count() -> int:
    return get_competitor_collection().count_documents({})
