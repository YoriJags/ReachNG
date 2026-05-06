"""
Instagram bio scraper for small business lead discovery.

Searches DuckDuckGo for Lagos-based IG business accounts in target niches,
fetches each public profile page, and extracts the WhatsApp number from the bio.
No login, no API key — public profile pages only.
"""
import asyncio
import re
from typing import Optional
import httpx
from config import get_settings
import structlog

log = structlog.get_logger()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ReachNG/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

# Niche search queries — finds Lagos IG business accounts via Google/DDG
NICHE_QUERIES = [
    "site:instagram.com Lagos skincare brand WhatsApp",
    "site:instagram.com Lagos fashion brand DM to order",
    "site:instagram.com Lagos food vendor WhatsApp order",
    "site:instagram.com Lagos interior decor WhatsApp",
    "site:instagram.com Lagos hair stylist book via WhatsApp",
    "site:instagram.com Lagos baker cake order WhatsApp",
    "site:instagram.com Lagos tailor bespoke DM",
    "site:instagram.com Lagos small business owner WhatsApp",
]

# Follower count tiers — used to score leads and decide whether to pitch
# <500:    hobby/side hustle — skip (can't afford retainer)
# 500-5K:  active small business — sweet spot
# 5K-50K:  serious merchant — high priority
# 50K+:    likely has social media manager — deprioritise
_FOLLOWER_MIN = 500    # drop below this
_FOLLOWER_CAP = 50000  # deprioritise above this

_WA_PATTERN = re.compile(
    r"(?:wa\.me/|whatsapp\.com/send\?phone=|whatsapp[:\s]+|📱[:\s]*|☎[:\s]*|📞[:\s]*)(\+?234\d{9,10}|\+?0[789]\d{9})",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(\+?234[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}|\+?0[789]\d{9})"
)


def _extract_whatsapp(text: str) -> Optional[str]:
    """Extract WhatsApp/phone number from profile text."""
    m = _WA_PATTERN.search(text)
    if m:
        return _normalise_phone(m.group(1))
    m = _PHONE_PATTERN.search(text)
    if m:
        return _normalise_phone(m.group(1))
    return None


def _normalise_phone(raw: str) -> str:
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("234"):
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+234" + digits[1:]
    return "+" + digits


def _extract_follower_count(html: str) -> Optional[int]:
    """Extract follower count from public IG profile HTML."""
    # IG embeds follower count in the meta description:
    # "1,234 Followers, 56 Following, 78 Posts"
    m = re.search(r"([\d,]+)\s+Followers", html, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    # JSON-LD / shared_data fallback: "edge_followed_by":{"count":1234}
    m2 = re.search(r'"edge_followed_by"\s*:\s*\{"count"\s*:\s*(\d+)', html)
    if m2:
        return int(m2.group(1))
    return None


def _follower_tier(n: Optional[int]) -> str:
    if n is None:        return "unknown"
    if n < 500:          return "hobby"
    if n < 5_000:        return "small"
    if n < 50_000:       return "serious"
    return "large"


def _follower_score(n: Optional[int]) -> int:
    """Additive lead score contribution from follower count."""
    if n is None:        return 0
    if n < 500:          return -20   # hobby — drag score down
    if n < 5_000:        return 20    # sweet spot
    if n < 50_000:       return 30    # serious
    return 5                          # large — present but low priority


def _extract_ig_handle(url: str) -> Optional[str]:
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", url)
    if m:
        handle = m.group(1)
        if handle.lower() in {"p", "reel", "stories", "explore", "tv", "accounts"}:
            return None
        return handle
    return None


async def _fetch_ig_profile(handle: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Fetch public Instagram profile page and extract bio + phone."""
    url = f"https://www.instagram.com/{handle}/"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code != 200:
            return None
        text = resp.text

        # Extract bio from meta description
        bio = ""
        m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', text)
        if m:
            bio = m.group(1)

        # Extract display name
        name = handle
        m2 = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', text)
        if m2:
            name = m2.group(1).split("•")[0].split("(")[0].strip()

        phone = _extract_whatsapp(bio + " " + text[:5000])
        if not phone:
            return None

        followers = _extract_follower_count(text)
        tier = _follower_tier(followers)

        # Drop hobby accounts — can't afford the retainer
        if followers is not None and followers < _FOLLOWER_MIN:
            log.debug("ig_lead_dropped_hobby", handle=handle, followers=followers)
            return None

        # Deprioritise large accounts (likely have a social media manager)
        if followers is not None and followers >= _FOLLOWER_CAP:
            priority = "low"
            tier_note = "Large account — may have social media manager"
        elif tier == "serious":
            priority = "high"
            tier_note = f"{followers:,} followers — serious merchant"
        elif tier == "small":
            priority = "medium"
            tier_note = f"{followers:,} followers — active small business (sweet spot)"
        else:
            priority = "medium"
            tier_note = "Follower count unknown"

        base_score = 50
        lead_score = max(10, min(100, base_score + _follower_score(followers)))

        return {
            "place_id": f"ig_{handle}",
            "name": name or handle,
            "vertical": "small_business",
            "source": "instagram",
            "phone": phone,
            "email": None,
            "address": "Lagos",
            "website": url,
            "domain": "instagram.com",
            "rating": None,
            "category": "Small Business",
            "contact_name": None,
            "contact_title": None,
            "linkedin_url": None,
            "enrichment": None,
            "lead_temperature": 1,
            "temperature_reason": tier_note,
            "ig_handle": handle,
            "ig_followers": followers,
            "ig_follower_tier": tier,
            "ig_priority": priority,
            "lead_score": lead_score,
            "bio": bio[:300],
        }
    except Exception as e:
        log.debug("ig_profile_fetch_failed", handle=handle, error=str(e))
        return None


def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results)) or []
    except Exception as e:
        log.error("ddg_ig_search_failed", error=str(e))
        return []


async def discover_ig_leads(
    max_results: int = 20,
    city_override: Optional[str] = None,
) -> list[dict]:
    """
    Discover Lagos small business IG accounts with WhatsApp numbers in their bio.
    Returns lead dicts compatible with the leads Mongo schema.
    """
    loop = asyncio.get_event_loop()

    # Run a few DDG queries in parallel to find IG profile URLs
    search_tasks = [
        loop.run_in_executor(None, _ddg_search_sync, q, 8)
        for q in NICHE_QUERIES[:5]
    ]
    all_raw = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Collect unique IG handles from results
    handles: list[str] = []
    seen: set[str] = set()
    for batch in all_raw:
        if isinstance(batch, Exception):
            continue
        for r in batch:
            url = r.get("href", "")
            handle = _extract_ig_handle(url)
            if handle and handle not in seen:
                seen.add(handle)
                handles.append(handle)

    if not handles:
        log.info("ig_discovery_no_handles")
        return []

    handles = handles[:max_results]

    # Fetch each profile and extract WhatsApp
    sem = asyncio.Semaphore(5)
    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        async def _fetch_one(h: str) -> Optional[dict]:
            async with sem:
                return await _fetch_ig_profile(h, client)

        results = await asyncio.gather(*[_fetch_one(h) for h in handles], return_exceptions=True)

    leads = []
    for item in results:
        if isinstance(item, Exception) or item is None:
            continue
        leads.append(item)

    log.info("ig_discovery_complete", count=len(leads))
    return leads
