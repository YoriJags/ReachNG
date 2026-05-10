"""
Social media lead discovery — Apify (Instagram, Facebook) + Twitter/X API v2.
Finds warm leads already talking about services we sell, or signalling buying intent.
These are NOT cold contacts — they've self-identified. Message opens far better.
"""
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import httpx
from database import get_db
from config import get_settings
import structlog

log = structlog.get_logger()

APIFY_BASE = "https://api.apify.com/v2"
TWITTER_BASE = "https://api.twitter.com/2"


# ── Per-vertical social config ────────────────────────────────────────────────

VERTICAL_SOCIAL = {
    "real_estate": {
        "ig_hashtags":      ["LagosRealEstate", "LagosProperty", "LekkiRealEstate", "VILagos", "NigeriaRealEstate", "LagosHomes"],
        "tt_hashtags":      ["lagosrealestate", "lagosproperty", "nigeriapropertymarket", "lekkiapartments", "buypropertylagos"],
        "twitter_queries":  ["Lagos real estate", "buy apartment Lekki", "looking for realtor Lagos", "property for sale Lagos island"],
        "fb_keywords":      ["Lagos real estate", "property Lagos", "house for sale Lagos"],
        "competitor_terms": ["estate agent Lagos", "property developer Lagos"],
    },
    "recruitment": {
        "ig_hashtags":      ["LagosJobs", "NigeriaJobs", "HiringLagos", "LagosRecruitment", "NigeriaCareer"],
        "tt_hashtags":      ["lagosjobs", "nigeriajobs", "hiringlagos", "jobsinnigeria", "recruitmentlagos"],
        "twitter_queries":  ["hiring Lagos", "job opening Nigeria", "recruitment Lagos", "looking for talent Lagos", "we are hiring Nigeria"],
        "fb_keywords":      ["jobs Lagos", "hiring Nigeria", "recruitment Lagos"],
        "competitor_terms": ["recruitment agency Lagos", "staffing Nigeria", "headhunter Lagos"],
    },
    "events": {
        "ig_hashtags":      ["LagosEvents", "LagosParty", "NaijaEvents", "LagosEntertainment", "EventsLagos", "LagosNightlife"],
        "tt_hashtags":      ["lagosevents", "naijaevents", "lagosparty", "eventplannerlagos", "corporateeventlagos"],
        "twitter_queries":  ["event planner Lagos", "corporate event Lagos", "event management Nigeria", "organise event Lagos"],
        "fb_keywords":      ["event planner Lagos", "event management Lagos"],
        "competitor_terms": ["event company Lagos", "event decorator Lagos"],
    },
    "fintech": {
        "ig_hashtags":      ["LagosFintech", "NigeriaFintech", "AfricanFintech", "LagosStartup", "NairaFinance"],
        "tt_hashtags":      ["nigeriafintech", "lagostech", "africanstartup", "nigeriastartup", "digitalpaymentsnigeria"],
        "twitter_queries":  ["fintech Lagos", "digital payments Nigeria", "startup funding Lagos", "raise investment Nigeria"],
        "fb_keywords":      ["fintech Nigeria", "startup Lagos"],
        "competitor_terms": ["payment solution Lagos", "digital lender Nigeria"],
    },
    "legal": {
        "ig_hashtags":      ["LagosLawyer", "NigeriaLaw", "LagosLegal", "NigerianLawyer", "LawyerLagos"],
        "tt_hashtags":      ["nigerianlawyer", "lagoslegal", "legaladvicenigeria", "nigerialaw", "corporatelawyerlagos"],
        "twitter_queries":  ["law firm Lagos", "legal advice Nigeria", "corporate lawyer Lagos", "need lawyer Lagos"],
        "fb_keywords":      ["lawyer Lagos", "legal services Nigeria"],
        "competitor_terms": ["law firm Lagos", "solicitor Lagos"],
    },
    "logistics": {
        "ig_hashtags":      ["LagosLogistics", "NigeriaLogistics", "LagosShipping", "LagosCourier", "FreightLagos"],
        "tt_hashtags":      ["lagoslogistics", "nigerialogistics", "freightlagos", "haulagelagos", "deliverylagos"],
        "twitter_queries":  ["logistics Lagos", "freight Lagos", "haulage Nigeria", "shipping Apapa", "trucking Lagos"],
        "fb_keywords":      ["logistics Lagos", "haulage Nigeria", "courier Lagos"],
        "competitor_terms": ["logistics company Lagos", "freight forwarder Apapa"],
    },
    "agriculture": {
        "ig_hashtags":      ["NigeriaAgriculture", "AgribusinessNigeria", "FarmingNigeria", "NigeriaFarm", "AgricNigeria"],
        "tt_hashtags":      ["nigeriafarming", "agribusinessnigeria", "farminginnigeria", "poultryfarmnigeria", "agrictok"],
        "twitter_queries":  ["agribusiness Nigeria", "farm produce Lagos", "poultry farm Nigeria", "food processing Nigeria", "agro commodity Nigeria"],
        "fb_keywords":      ["agribusiness Nigeria", "farm produce Lagos", "poultry Nigeria"],
        "competitor_terms": ["agribusiness company Nigeria", "farm produce supplier Lagos"],
    },
    "small_business": {
        "ig_hashtags":      ["LagosSmallBusiness", "LagosEntrepreneur", "MadeInLagos", "LagosBusiness", "NaijaFashion", "LagosFood", "LagosBeauty"],
        "tt_hashtags":      ["lagossmallbusiness", "lagosvendor", "lagosskincare", "lagosfashion", "lagosfoods", "nigeriaentrepreneur"],
        "twitter_queries":  [
            "Lagos small business WhatsApp order",
            "DM to order Lagos fashion",
            "Lagos skincare brand order WhatsApp",
            "Lagos food vendor order DM",
            "Lagos bespoke tailor WhatsApp",
        ],
        "fb_keywords":      ["Lagos small business", "Lagos vendor", "Lagos DM to order"],
        "competitor_terms": ["Lagos business WhatsApp", "order via DM Lagos"],
        # WhatsApp directory search terms (used by scrape_wa_directories)
        "wa_dir_queries":   [
            "Lagos fashion skincare beauty WhatsApp business",
            "Lagos food vendor baker catering WhatsApp",
            "Lagos tailor interior decor events WhatsApp",
        ],
    },
    "hospitality": {
        "ig_hashtags":      ["LagosRestaurant", "LagosBar", "LagosLounge", "LagosNightlife", "LagosRooftop", "LagosEat"],
        "tt_hashtags":      ["lagosrestaurant", "lagosbar", "lagoslounge", "lagosparty", "eatinginlagos"],
        "twitter_queries":  [
            "Lagos restaurant reservation WhatsApp",
            "Lagos bar lounge booking table",
            "rooftop bar Lagos reservation",
            "event venue Lagos booking",
        ],
        "fb_keywords":      ["Lagos restaurant", "Lagos bar lounge", "Lagos event venue"],
        "competitor_terms": ["restaurant booking Lagos", "bar reservation Lagos"],
        "wa_dir_queries":   ["Lagos restaurant bar lounge WhatsApp reservation"],
    },
}


# ── Database ──────────────────────────────────────────────────────────────────

def get_signals_col():
    return get_db()["social_signals"]


def ensure_social_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_signals_col()
    col.create_index([("signal_id", ASCENDING)], unique=True)
    col.create_index([("vertical", ASCENDING)])
    col.create_index([("platform", ASCENDING)])
    col.create_index([("found_at", DESCENDING)])
    col.create_index([("converted", ASCENDING)])


def _is_seen(signal_id: str) -> bool:
    return get_signals_col().count_documents({"signal_id": signal_id}) > 0


def _save_signal(signal: dict):
    try:
        get_signals_col().insert_one({**signal, "found_at": datetime.now(timezone.utc), "converted": False})
    except Exception:
        pass  # duplicate signal_id — already saved


def get_social_signals(vertical: str | None = None, limit: int = 50) -> list[dict]:
    query = {}
    if vertical:
        query["vertical"] = vertical
    return list(get_signals_col().find(query, {"_id": 0}).sort("found_at", -1).limit(limit))


def mark_signal_converted(signal_id: str):
    get_signals_col().update_one({"signal_id": signal_id}, {"$set": {"converted": True}})


# ── Contact extraction helpers ────────────────────────────────────────────────

_NIGERIAN_PHONE_RE = re.compile(r'(\+?234[789]\d{9}|0[789]\d{9})')
_EMAIL_RE          = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_URL_RE            = re.compile(r'https?://\S+|www\.\S+')


def _extract_contact(text: str) -> dict:
    """Pull phone, email, website from bio or post caption."""
    text = text or ""
    phone   = m.group(0) if (m := _NIGERIAN_PHONE_RE.search(text)) else None
    email   = m.group(0) if (m := _EMAIL_RE.search(text)) else None
    website = m.group(0) if (m := _URL_RE.search(text)) else None
    # Normalise to international format
    if phone and phone.startswith("0"):
        phone = "+234" + phone[1:]
    return {"phone": phone, "email": email, "website": website}


def _make_place_id(platform: str, username: str) -> str:
    slug = re.sub(r'\W+', '_', username.lower())
    return f"social_{platform}_{slug}"


def _normalise_lead(
    *,
    platform: str,
    vertical: str,
    username: str,
    display_name: str,
    bio: str = "",
    post_text: str = "",
    profile_url: str = "",
    follower_count: int = 0,
    signal_id: str,
) -> dict:
    """Return a lead dict compatible with the campaign pipeline."""
    combined_text = f"{bio} {post_text}"
    contact = _extract_contact(combined_text)
    return {
        "place_id":      _make_place_id(platform, username),
        "name":          display_name or username,
        "phone":         contact["phone"],
        "email":         contact["email"],
        "website":       contact["website"],
        "address":       None,
        "category":      platform,
        "rating":        None,
        # Social-specific fields
        "source":        "social",
        "platform":      platform,
        "post_text":     post_text,
        "profile_url":   profile_url,
        "follower_count": follower_count,
        "signal_id":     signal_id,
    }


# ── Apify helpers ─────────────────────────────────────────────────────────────

async def _run_apify(actor_id: str, input_data: dict) -> list[dict]:
    """Run an Apify actor synchronously and return dataset items."""
    settings = get_settings()
    if not settings.apify_api_token:
        log.debug("apify_skipped_no_token")
        return []

    url    = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": settings.apify_api_token, "timeout": 120, "memory": 256}

    try:
        async with httpx.AsyncClient(timeout=130) as client:
            r = await client.post(url, json=input_data, params=params)
            if r.status_code != 200:
                log.warning("apify_error", actor=actor_id, status=r.status_code, body=r.text[:200])
                return []
            return r.json() if isinstance(r.json(), list) else []
    except Exception as e:
        log.error("apify_request_failed", actor=actor_id, error=str(e))
        return []


# ── Twitter/X — DDG-based (no Apify, no API key) ─────────────────────────────

def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results)) or []
    except Exception as e:
        log.error("ddg_social_search_failed", error=str(e))
        return []


async def scrape_twitter_ddg(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Find Lagos business Twitter accounts via DDG — no API key needed.
    Strategy: DDG site:twitter.com queries → extract handle from URL →
    snippet often contains bio text with phone numbers.
    """
    config  = VERTICAL_SOCIAL.get(vertical, {})
    queries = config.get("twitter_queries", [])
    if not queries:
        return []

    loop = asyncio.get_event_loop()
    # Run top 3 queries in parallel
    tasks = [
        loop.run_in_executor(None, _ddg_search_sync, f"site:twitter.com {q}", 8)
        for q in queries[:3]
    ]
    all_raw = await asyncio.gather(*tasks, return_exceptions=True)

    leads: list[dict] = []
    seen: set[str] = set()

    for batch in all_raw:
        if isinstance(batch, Exception):
            continue
        for r in batch:
            url     = r.get("href", "")
            snippet = r.get("body", "") or r.get("description", "")
            title   = r.get("title", "")

            # Extract Twitter handle from URL
            m = re.search(r"twitter\.com/([A-Za-z0-9_]+)(?:/|$)", url)
            if not m:
                continue
            username = m.group(1)
            if username.lower() in {"search", "hashtag", "i", "home", "explore", "notifications"}:
                continue
            if username in seen:
                continue
            seen.add(username)

            signal_id = f"tw_ddg_{username}"
            if _is_seen(signal_id):
                continue

            combined = f"{title} {snippet}"
            contact  = _extract_contact(combined)

            # Only keep if we found a phone — cold Twitter profile with no contact is low value
            if not contact["phone"] and not contact["email"]:
                continue

            lead = _normalise_lead(
                platform="twitter",
                vertical=vertical,
                username=username,
                display_name=title.split("(")[0].strip() or username,
                bio=snippet[:300],
                post_text="",
                profile_url=f"https://twitter.com/{username}",
                follower_count=0,
                signal_id=signal_id,
            )
            lead["phone"]  = contact["phone"]
            lead["email"]  = contact["email"]
            lead["website"] = contact["website"]
            _save_signal({**lead, "vertical": vertical, "signal_id": signal_id})
            leads.append(lead)

    log.info("twitter_ddg_found", vertical=vertical, count=len(leads))
    return leads


# ── WhatsApp Business Directories ─────────────────────────────────────────────

# These sites aggregate WhatsApp business numbers by category/city.
# DDG finds them and we extract numbers directly from search snippets.
_WA_DIR_SITES = [
    "wasap.my",
    "wabiz.org",
    "wa.link",
    "api.whatsapp.com/send",
]

async def scrape_wa_directories(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Search WhatsApp business directory sites for Lagos businesses in this vertical.
    These sites list businesses with their WhatsApp links — direct phone number extraction.
    No profile fetch needed — DDG snippet usually contains the number.
    """
    config  = VERTICAL_SOCIAL.get(vertical, {})
    queries = config.get("wa_dir_queries", [])
    if not queries:
        return []

    loop = asyncio.get_event_loop()
    # Also run a direct wa.me search
    wa_queries = queries + [
        f"site:wasap.my Lagos {vertical.replace('_', ' ')}",
        f"wa.me/234 Lagos {vertical.replace('_', ' ')} business",
    ]
    tasks = [
        loop.run_in_executor(None, _ddg_search_sync, q, 6)
        for q in wa_queries[:4]
    ]
    all_raw = await asyncio.gather(*tasks, return_exceptions=True)

    _WA_RE = re.compile(
        r"(?:wa\.me/|whatsapp\.com/send\?phone=|wasap\.my/)(\+?234\d{9,10}|234\d{9,10})"
    )
    _PHONE_RE = re.compile(r"(\+?234[789]\d{9}|0[789]\d{9})")

    leads: list[dict] = []
    seen: set[str] = set()

    for batch in all_raw:
        if isinstance(batch, Exception):
            continue
        for r in batch:
            url     = r.get("href", "")
            snippet = r.get("body", "") or r.get("description", "")
            title   = r.get("title", "")
            combined = f"{url} {title} {snippet}"

            # Extract phone
            phone = None
            m = _WA_RE.search(combined)
            if m:
                digits = re.sub(r"\D", "", m.group(1))
                phone  = f"+{digits}" if not digits.startswith("+") else digits
                if not phone.startswith("+234"):
                    phone = "+234" + phone.lstrip("+")
            if not phone:
                m2 = _PHONE_RE.search(combined)
                if m2:
                    raw = m2.group(1)
                    digits = re.sub(r"\D", "", raw)
                    phone  = ("+234" + digits[1:]) if digits.startswith("0") else ("+" + digits)

            if not phone or phone in seen:
                continue
            seen.add(phone)

            signal_id = f"wa_dir_{re.sub(r'[^a-z0-9]', '_', phone)}"
            if _is_seen(signal_id):
                continue

            name = title.split("|")[0].split("-")[0].strip() or "Lagos Business"
            lead = _normalise_lead(
                platform="wa_directory",
                vertical=vertical,
                username=phone,
                display_name=name,
                bio=snippet[:300],
                post_text="",
                profile_url=url,
                follower_count=0,
                signal_id=signal_id,
            )
            lead["phone"]  = phone
            lead["source"] = "wa_directory"
            lead["temperature_reason"] = "WhatsApp business directory listing"
            lead["lead_temperature"] = 1
            _save_signal({**lead, "vertical": vertical, "signal_id": signal_id})
            leads.append(lead)

            if len(leads) >= max_results:
                break

    log.info("wa_directory_found", vertical=vertical, count=len(leads))
    return leads


# ── Instagram (Apify) ─────────────────────────────────────────────────────────

async def scrape_instagram_hashtags(vertical: str, max_results: int = 20) -> list[dict]:
    """Find business accounts posting under vertical-relevant hashtags."""
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    config   = VERTICAL_SOCIAL.get(vertical, {})
    hashtags = config.get("ig_hashtags", [])
    if not hashtags:
        return []

    items = await _run_apify("apify/instagram-scraper", {
        "hashtags":     hashtags,
        "resultsType":  "posts",
        "resultsLimit": max_results,
    })

    leads = []
    for item in items:
        username     = item.get("ownerUsername") or item.get("username", "")
        display_name = item.get("ownerFullName") or item.get("fullName") or username
        caption      = item.get("caption") or item.get("text", "")
        profile_url  = f"https://instagram.com/{username}"
        signal_id    = f"ig_{username}_{item.get('id', caption[:20])}"

        if not username or _is_seen(signal_id):
            continue

        lead = _normalise_lead(
            platform="instagram",
            vertical=vertical,
            username=username,
            display_name=display_name,
            post_text=caption,
            profile_url=profile_url,
            follower_count=item.get("ownerFollowersCount", 0),
            signal_id=signal_id,
        )
        _save_signal({**lead, "vertical": vertical, "signal_id": signal_id, "raw_caption": caption})
        leads.append(lead)

    log.info("ig_leads_found", vertical=vertical, count=len(leads))
    return leads


# ── Twitter / X (Apify) ───────────────────────────────────────────────────────

async def scrape_twitter_leads(vertical: str, max_results: int = 20) -> list[dict]:
    """Search Twitter/X for intent-signalling tweets in a vertical."""
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    config  = VERTICAL_SOCIAL.get(vertical, {})
    queries = config.get("twitter_queries", [])
    if not queries:
        return []

    # Combine queries with Lagos filter — we only want Lagos signal
    search_terms = [f"{q} Lagos" for q in queries[:3]]

    items = await _run_apify("apidojo/tweet-scraper", {
        "searchTerms": search_terms,
        "maxItems":    max_results,
        "sort":        "Latest",
        "tweetLanguage": "en",
    })

    leads = []
    for item in items:
        author      = item.get("author") or {}
        username    = author.get("userName") or item.get("user", {}).get("screen_name", "")
        display_name = author.get("name") or item.get("user", {}).get("name", username)
        tweet_text  = item.get("text") or item.get("full_text", "")
        bio         = author.get("description") or item.get("user", {}).get("description", "")
        profile_url = f"https://twitter.com/{username}"
        signal_id   = f"tw_{item.get('id') or item.get('id_str', username + tweet_text[:20])}"
        followers   = author.get("followers") or item.get("user", {}).get("followers_count", 0)

        if not username or _is_seen(signal_id):
            continue

        # Skip pure retweets — original signal only
        if tweet_text.startswith("RT @"):
            continue

        lead = _normalise_lead(
            platform="twitter",
            vertical=vertical,
            username=username,
            display_name=display_name,
            bio=bio,
            post_text=tweet_text,
            profile_url=profile_url,
            follower_count=followers,
            signal_id=signal_id,
        )
        _save_signal({**lead, "vertical": vertical, "signal_id": signal_id, "raw_tweet": tweet_text})
        leads.append(lead)

    log.info("twitter_leads_found", vertical=vertical, count=len(leads))
    return leads


# ── Twitter/X API v2 (direct — backup / premium tier) ────────────────────────

async def scrape_twitter_api(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Use Twitter API v2 Bearer Token directly (requires $100/month Basic plan).
    Falls back silently if token not set — Apify actor is used instead.
    """
    settings = get_settings()
    if not settings.twitter_bearer_token:
        return []

    config  = VERTICAL_SOCIAL.get(vertical, {})
    queries = config.get("twitter_queries", [])
    if not queries:
        return []

    # Build OR query for Twitter search
    q = " OR ".join(f'"{q}"' for q in queries[:3]) + " lang:en -is:retweet"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{TWITTER_BASE}/tweets/search/recent",
                headers={"Authorization": f"Bearer {settings.twitter_bearer_token}"},
                params={
                    "query":        q,
                    "max_results":  min(max_results, 100),
                    "tweet.fields": "author_id,text,created_at",
                    "expansions":   "author_id",
                    "user.fields":  "username,name,description,public_metrics",
                },
            )
            if r.status_code != 200:
                log.warning("twitter_api_error", status=r.status_code)
                return []

        data  = r.json()
        tweets = data.get("data", [])
        users  = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
        leads  = []

        for tweet in tweets:
            user     = users.get(tweet.get("author_id"), {})
            username = user.get("username", "")
            signal_id = f"twapi_{tweet['id']}"

            if not username or _is_seen(signal_id):
                continue

            lead = _normalise_lead(
                platform="twitter",
                vertical=vertical,
                username=username,
                display_name=user.get("name", username),
                bio=user.get("description", ""),
                post_text=tweet.get("text", ""),
                profile_url=f"https://twitter.com/{username}",
                follower_count=user.get("public_metrics", {}).get("followers_count", 0),
                signal_id=signal_id,
            )
            _save_signal({**lead, "vertical": vertical, "signal_id": signal_id})
            leads.append(lead)

        log.info("twitter_api_leads_found", vertical=vertical, count=len(leads))
        return leads

    except Exception as e:
        log.error("twitter_api_failed", error=str(e))
        return []


# ── Facebook (Apify) ──────────────────────────────────────────────────────────

async def scrape_facebook_mentions(vertical: str, max_results: int = 20) -> list[dict]:
    """Scrape Facebook pages and groups for vertical-relevant businesses."""
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    config   = VERTICAL_SOCIAL.get(vertical, {})
    keywords = config.get("fb_keywords", [])
    if not keywords:
        return []

    items = await _run_apify("apify/facebook-posts-scraper", {
        "startUrls": [
            {"url": f"https://www.facebook.com/search/posts?q={kw.replace(' ', '%20')}"}
            for kw in keywords[:2]
        ],
        "resultsLimit": max_results,
    })

    leads = []
    for item in items:
        username     = item.get("pageName") or item.get("username") or item.get("pageId", "")
        display_name = item.get("pageName") or item.get("title") or item.get("name") or username
        about        = item.get("text") or item.get("about") or item.get("description", "")
        page_url     = item.get("url") or item.get("pageUrl") or f"https://facebook.com/{username}"
        signal_id    = f"fb_{item.get('postId') or item.get('pageId') or username}"
        followers    = item.get("likes") or item.get("followers", 0)

        if not username or _is_seen(signal_id):
            continue

        lead = _normalise_lead(
            platform="facebook",
            vertical=vertical,
            username=username,
            display_name=display_name,
            bio=about,
            post_text=about,
            profile_url=page_url,
            follower_count=followers,
            signal_id=signal_id,
        )
        _save_signal({**lead, "vertical": vertical, "signal_id": signal_id})
        leads.append(lead)

    log.info("fb_leads_found", vertical=vertical, count=len(leads))
    return leads


# ── TikTok (Apify) ───────────────────────────────────────────────────────────

async def scrape_tiktok_leads(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Find businesses posting on TikTok under vertical-relevant hashtags.
    TikTok is massive for Nigerian SMEs — product demos, service showcases,
    business pitches all happen there. High intent signal.
    """
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    config   = VERTICAL_SOCIAL.get(vertical, {})
    hashtags = config.get("tt_hashtags", [])
    if not hashtags:
        return []

    items = await _run_apify("clockworks/tiktok-scraper", {
        "hashtags":   hashtags[:4],
        "resultsPerPage": max_results,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
    })

    leads = []
    for item in items:
        author       = item.get("authorMeta") or {}
        username     = author.get("name") or item.get("author", "")
        display_name = author.get("nickName") or username
        bio          = author.get("signature") or ""
        caption      = item.get("text") or ""
        profile_url  = f"https://tiktok.com/@{username}"
        signal_id    = f"tt_{item.get('id') or username + caption[:15]}"
        followers    = author.get("fans") or 0

        if not username or _is_seen(signal_id):
            continue

        lead = _normalise_lead(
            platform="tiktok",
            vertical=vertical,
            username=username,
            display_name=display_name,
            bio=bio,
            post_text=caption,
            profile_url=profile_url,
            follower_count=followers,
            signal_id=signal_id,
        )
        _save_signal({**lead, "vertical": vertical, "signal_id": signal_id, "raw_caption": caption})
        leads.append(lead)

    log.info("tiktok_leads_found", vertical=vertical, count=len(leads))
    return leads


# ── Competitor mention monitoring ─────────────────────────────────────────────

async def monitor_competitor_mentions(
    vertical: str,
    competitors: list[str] | None = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Monitor Twitter/X for people asking about competitors or services.
    These are the hottest leads — already in-market, evaluating options.
    E.g. "Does anyone recommend a good recruitment agency in Lagos?"
    """
    config      = VERTICAL_SOCIAL.get(vertical, {})
    comp_terms  = competitors or config.get("competitor_terms", [])
    if not comp_terms:
        return []

    items = await _run_apify("apidojo/tweet-scraper", {
        "searchTerms": comp_terms[:3],
        "maxItems":    max_results,
        "sort":        "Latest",
    })

    leads = []
    for item in items:
        author      = item.get("author") or {}
        username    = author.get("userName") or ""
        display_name = author.get("name") or username
        tweet_text  = item.get("text") or ""
        bio         = author.get("description") or ""
        signal_id   = f"comp_{item.get('id', username + tweet_text[:15])}"

        if not username or _is_seen(signal_id) or tweet_text.startswith("RT @"):
            continue

        lead = _normalise_lead(
            platform="twitter",
            vertical=vertical,
            username=username,
            display_name=display_name,
            bio=bio,
            post_text=tweet_text,
            profile_url=f"https://twitter.com/{username}",
            follower_count=author.get("followers", 0),
            signal_id=signal_id,
        )
        signal_data = {**lead, "vertical": vertical, "signal_id": signal_id, "signal_type": "competitor_mention"}
        _save_signal(signal_data)
        leads.append(lead)

    log.info("competitor_mentions_found", vertical=vertical, count=len(leads))
    return leads


# ── Main entry: discover from all sources ────────────────────────────────────

async def discover_social_leads(
    vertical: str,
    max_results: int = 60,
    include_competitor_monitoring: bool = True,
) -> list[dict]:
    """
    Aggregate social leads from Instagram, Twitter (Apify + API), and Facebook.
    Returns unified lead list compatible with the campaign pipeline.
    """
    per_source  = max(5, max_results // 4)
    comp_quota  = per_source if include_competitor_monitoring else 0

    tasks = [
        scrape_twitter_ddg(vertical, per_source),       # DDG-based, always runs
        scrape_wa_directories(vertical, per_source),    # WhatsApp directory scraper
        scrape_instagram_hashtags(vertical, per_source), # Apify — no-ops if no token
        scrape_tiktok_leads(vertical, per_source),       # Apify — no-ops if no token
        scrape_twitter_leads(vertical, per_source),      # Apify — no-ops if no token
        scrape_twitter_api(vertical, per_source),        # no-ops if no Bearer token
        scrape_facebook_mentions(vertical, per_source),  # Apify — no-ops if no token
    ]
    if comp_quota:
        tasks.append(monitor_competitor_mentions(vertical, max_results=comp_quota))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    from tools.memory import score_temperature

    seen_ids = set()
    leads    = []
    for r in results:
        if isinstance(r, Exception):
            log.error("social_source_error", error=str(r))
            continue
        for lead in r:
            pid = lead["place_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                # Score temperature from bio + any post text attached to the lead
                bio_text = lead.get("bio", "") or lead.get("description", "") or ""
                post_text = lead.get("post_text", "") or ""
                temp, reason = score_temperature(bio_text + " " + post_text)
                # Social leads are at least warm by nature — they self-identified
                if temp == 0:
                    temp, reason = 1, "social_self_identified"
                lead["lead_temperature"] = temp
                lead["temperature_reason"] = reason
                leads.append(lead)

    hot_count  = sum(1 for l in leads if l.get("lead_temperature", 0) == 2)
    warm_count = sum(1 for l in leads if l.get("lead_temperature", 0) == 1)
    log.info("social_discovery_total", vertical=vertical, total=len(leads),
             hot=hot_count, warm=warm_count)
    return leads[:max_results]
