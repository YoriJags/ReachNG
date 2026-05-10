"""
Signal Intelligence — cross-platform hot lead detection.

Monitors active signals across:
  1. Facebook Ads Library — businesses actively spending on ads RIGHT NOW
  2. LinkedIn (via Apollo signals — hiring posts, funding rounds)
  3. Twitter/X — businesses announcing growth, hiring, launches
  4. Instagram — business accounts with recent high-signal posts
  5. TikTok — brands with recent product/launch content
  6. Google Trends proxy — rising search interest in a vertical/brand

Each source returns leads with lead_temperature=2 (hot) or 1 (warm)
and a temperature_reason explaining why.

All sources are optional — skipped silently if tokens are missing.
"""
import asyncio
import hashlib
import httpx
from datetime import datetime, timezone
from typing import Optional
import structlog
from config import get_settings

log = structlog.get_logger()

# ── Hot signal phrases (cross-platform) ──────────────────────────────────────
# These phrases in any bio, post, or ad copy = hot lead (temperature 2)
HOT_PHRASES = [
    # Hiring / growth
    "we are hiring", "we're hiring", "now hiring", "hiring now", "join our team",
    "we are recruiting", "open positions", "job opening", "seeking talent",
    # Expansion / new locations
    "just launched", "grand opening", "new branch", "new location", "second location",
    "now open", "opening soon", "just opened", "expansion", "expanding to",
    # Funding / investment signals
    "just raised", "series a", "series b", "pre-seed", "seed round",
    "secured funding", "investment round", "seeking investment", "investor deck",
    # Client acquisition intent
    "looking for clients", "seeking clients", "taking on new clients",
    "accepting new projects", "open for business", "dm for business",
    # Product / service launches
    "introducing our", "launching our", "new product", "new service",
    "announcing our", "excited to announce",
]

# Warm signal phrases — worth reaching out, active business
WARM_PHRASES = [
    "celebrating", "milestone", "anniversary", "award", "recognition",
    "partnership", "collaboration", "working with", "proud to",
    "recently moved", "new office", "new team", "growing team",
    "new project", "upcoming event", "registration open",
]

FB_ADS_BASE   = "https://graph.facebook.com/v19.0/ads_archive"
TWITTER_BASE  = "https://api.twitter.com/2"
APIFY_BASE    = "https://api.apify.com/v2"

# ── Vertical → ad/search keywords ────────────────────────────────────────────
VERTICAL_AD_KEYWORDS: dict[str, list[str]] = {
    "real_estate":   ["Lagos property", "Lagos apartment", "real estate Lagos", "Lagos housing", "buy land Lagos"],
    "recruitment":   ["hiring Lagos", "recruitment Nigeria", "HR consulting Lagos", "staffing Nigeria"],
    "events":        ["event planner Lagos", "Lagos event", "corporate event Nigeria", "wedding planner Lagos"],
    "fintech":       ["fintech Nigeria", "digital lending", "microfinance Lagos", "investment Nigeria", "loan app Nigeria"],
    "legal":         ["law firm Lagos", "legal services Nigeria", "corporate lawyer Lagos", "solicitor Nigeria"],
    "logistics":     ["logistics Nigeria", "haulage Lagos", "cargo Lagos", "delivery company Nigeria", "freight Nigeria"],
    "agriculture":   ["agribusiness Nigeria", "farm produce Lagos", "food processing Nigeria", "agro Nigeria"],
    "agency_sales":  ["digital marketing Lagos", "consulting Lagos", "business services Nigeria", "outsourcing Nigeria"],
}


def _make_place_id(platform: str, identifier: str) -> str:
    """Generate a stable pseudo place_id for social/ads sources."""
    return hashlib.md5(f"{platform}:{identifier}".encode()).hexdigest()


def _score_text(text: str) -> tuple[int, Optional[str]]:
    """Return (temperature, reason) from any text."""
    if not text:
        return 0, None
    lower = text.lower()
    for phrase in HOT_PHRASES:
        if phrase in lower:
            return 2, phrase
    for phrase in WARM_PHRASES:
        if phrase in lower:
            return 1, phrase
    return 0, None


# ── 1. Facebook Ads Library ───────────────────────────────────────────────────

async def discover_fb_ads(vertical: str, max_results: int = 30) -> list[dict]:
    """
    Query Facebook Ads Library for active Nigerian advertisers in this vertical.
    Requires FB_ADS_ACCESS_TOKEN env var — skipped if missing.

    How to get a token:
      1. Go to developers.facebook.com → My Apps → Create App (Business)
      2. Add "Marketing API" product
      3. Generate a User Access Token with ads_read permission
      4. Extend to 60-day token via Graph API Explorer → /oauth/access_token?grant_type=fb_exchange_token
      5. Set FB_ADS_ACCESS_TOKEN in Railway env vars
    """
    settings = get_settings()
    token = settings.fb_ads_access_token
    if not token:
        log.debug("fb_ads_skip", reason="FB_ADS_ACCESS_TOKEN not set")
        return []

    keywords = VERTICAL_AD_KEYWORDS.get(vertical, VERTICAL_AD_KEYWORDS["agency_sales"])
    leads: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20.0) as client:
        for keyword in keywords[:3]:  # 3 keywords to stay within rate limits
            if len(leads) >= max_results:
                break
            try:
                resp = await client.get(
                    FB_ADS_BASE,
                    params={
                        "access_token":       token,
                        "search_terms":       keyword,
                        "ad_reached_countries": "NG",
                        "ad_delivery_status": "ACTIVE",
                        "ad_type":            "ALL",
                        "fields":             "page_name,page_id,ad_creative_bodies,ad_creative_link_descriptions,ad_snapshot_url",
                        "limit":              25,
                    },
                )
                if resp.status_code == 401:
                    log.warning("fb_ads_auth_error", msg="Token expired or invalid. Regenerate FB_ADS_ACCESS_TOKEN.")
                    break
                if resp.status_code != 200:
                    log.warning("fb_ads_error", status=resp.status_code, keyword=keyword)
                    continue

                data = resp.json()
                for ad in data.get("data", []):
                    page_id   = str(ad.get("page_id", ""))
                    page_name = ad.get("page_name", "")
                    if not page_id or page_id in seen:
                        continue
                    seen.add(page_id)

                    # Extract text from ad copy for signal scoring
                    bodies = " ".join(ad.get("ad_creative_bodies", []) or [])
                    descs  = " ".join(ad.get("ad_creative_link_descriptions", []) or [])
                    ad_text = bodies + " " + descs

                    # Any active ad = hot lead (they're spending money right now)
                    temp, reason = _score_text(ad_text)
                    if temp < 2:
                        temp, reason = 2, "active_fb_ad_spend"

                    leads.append({
                        "place_id":          _make_place_id("fb_ads", page_id),
                        "name":              page_name,
                        "vertical":          vertical,
                        "source":            "signal",
                        "platform":          "facebook_ads",
                        "phone":             None,
                        "website":           None,
                        "address":           None,
                        "rating":            None,
                        "category":          vertical.replace("_", " ").title(),
                        "lead_temperature":  temp,
                        "temperature_reason": reason,
                        "signal_url":        ad.get("ad_snapshot_url"),
                        "bio":               ad_text[:500],
                    })

            except Exception as e:
                log.error("fb_ads_request_failed", keyword=keyword, error=str(e))

    log.info("fb_ads_discovery", vertical=vertical, found=len(leads))
    return leads[:max_results]


# ── 2. Twitter/X signal discovery ────────────────────────────────────────────

async def discover_twitter_signals(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Search recent tweets from Nigerian businesses with growth signals.
    Requires TWITTER_BEARER_TOKEN — skipped if missing.
    """
    settings = get_settings()
    token = settings.twitter_bearer_token
    if not token:
        return []

    keywords = VERTICAL_AD_KEYWORDS.get(vertical, [])[:2]
    leads: list[dict] = []
    seen: set[str] = set()

    # Build query: keyword + Nigeria geo OR .ng domain OR Nigeria hashtag + has:links (business accounts more likely to have links)
    async with httpx.AsyncClient(timeout=15.0) as client:
        for kw in keywords:
            if len(leads) >= max_results:
                break
            query = f'"{kw}" (Nigeria OR Lagos OR "Nigeria" OR ".ng") has:links -is:retweet lang:en'
            try:
                resp = await client.get(
                    f"{TWITTER_BASE}/tweets/search/recent",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "query": query,
                        "max_results": 20,
                        "tweet.fields": "author_id,text,entities",
                        "expansions": "author_id",
                        "user.fields": "name,username,description,url,public_metrics",
                    },
                )
                if resp.status_code != 200:
                    log.warning("twitter_signal_error", status=resp.status_code, kw=kw)
                    continue

                data = resp.json()
                users_map = {u["id"]: u for u in (data.get("includes", {}).get("users") or [])}

                for tweet in (data.get("data") or []):
                    author_id = tweet.get("author_id", "")
                    if author_id in seen:
                        continue
                    seen.add(author_id)

                    user = users_map.get(author_id, {})
                    bio  = user.get("description", "") or ""
                    text = tweet.get("text", "")
                    combined = bio + " " + text

                    temp, reason = _score_text(combined)
                    if temp == 0:
                        continue  # Only keep warm/hot from Twitter

                    leads.append({
                        "place_id":          _make_place_id("twitter", author_id),
                        "name":              user.get("name", "Unknown"),
                        "vertical":          vertical,
                        "source":            "signal",
                        "platform":          "twitter",
                        "phone":             None,
                        "website":           user.get("url"),
                        "address":           None,
                        "rating":            None,
                        "category":          vertical.replace("_", " ").title(),
                        "lead_temperature":  temp,
                        "temperature_reason": reason,
                        "bio":               bio,
                        "post_text":         text,
                    })

            except Exception as e:
                log.error("twitter_signal_failed", kw=kw, error=str(e))

    log.info("twitter_signals", vertical=vertical, found=len(leads))
    return leads[:max_results]


# ── 3. Instagram / TikTok signal discovery (via Apify) ───────────────────────

async def discover_ig_signals(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Scrape Instagram business profiles with hot signal keywords via Apify.
    Requires APIFY_API_TOKEN — skipped if missing.

    Apify-spend gated to IG-native verticals only (see tools.apify_gate).
    """
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    settings = get_settings()
    token = settings.apify_api_token
    if not token:
        return []

    # Use keyword search across IG profiles / hashtags
    keywords = VERTICAL_AD_KEYWORDS.get(vertical, [])[:2]
    leads: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=60.0) as client:
        for kw in keywords:
            if len(leads) >= max_results:
                break
            try:
                # Run apify/instagram-hashtag-scraper with signal keywords
                run_resp = await client.post(
                    f"{APIFY_BASE}/acts/apify~instagram-hashtag-scraper/run-sync-get-dataset-items",
                    params={"token": token},
                    json={
                        "hashtags": [kw.replace(" ", "").lower()],
                        "resultsLimit": 20,
                    },
                    timeout=55.0,
                )
                if run_resp.status_code not in (200, 201):
                    continue

                for item in run_resp.json():
                    owner = item.get("ownerUsername") or item.get("owner", {}).get("username", "")
                    if not owner or owner in seen:
                        continue
                    seen.add(owner)

                    bio  = item.get("biography", "") or item.get("ownerBio", "") or ""
                    cap  = item.get("caption", "") or ""
                    combined = bio + " " + cap

                    temp, reason = _score_text(combined)
                    if temp == 0:
                        temp, reason = 1, "ig_business_post"  # IG biz posting = at least warm

                    full_name = item.get("ownerFullName") or item.get("displayName") or owner
                    leads.append({
                        "place_id":          _make_place_id("instagram", owner),
                        "name":              full_name,
                        "vertical":          vertical,
                        "source":            "signal",
                        "platform":          "instagram",
                        "phone":             None,
                        "website":           None,
                        "address":           None,
                        "rating":            None,
                        "category":          vertical.replace("_", " ").title(),
                        "lead_temperature":  temp,
                        "temperature_reason": reason,
                        "bio":               bio,
                        "post_text":         cap,
                    })

            except Exception as e:
                log.error("ig_signal_failed", kw=kw, error=str(e))

    log.info("ig_signals", vertical=vertical, found=len(leads))
    return leads[:max_results]


async def discover_tiktok_signals(vertical: str, max_results: int = 15) -> list[dict]:
    """
    Scrape TikTok business posts with hot signal keywords via Apify.
    Requires APIFY_API_TOKEN — skipped if missing.

    Apify-spend gated to IG-native verticals only (see tools.apify_gate).
    """
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    settings = get_settings()
    token = settings.apify_api_token
    if not token:
        return []

    keywords = VERTICAL_AD_KEYWORDS.get(vertical, [])[:2]
    leads: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=60.0) as client:
        for kw in keywords:
            if len(leads) >= max_results:
                break
            try:
                run_resp = await client.post(
                    f"{APIFY_BASE}/acts/clockworks~tiktok-scraper/run-sync-get-dataset-items",
                    params={"token": token},
                    json={
                        "hashtags": [kw.replace(" ", "").lower()],
                        "maxProfilesPerQuery": 20,
                    },
                    timeout=55.0,
                )
                if run_resp.status_code not in (200, 201):
                    continue

                for item in run_resp.json():
                    author = item.get("authorMeta", {}) or {}
                    username = author.get("name") or author.get("id", "")
                    if not username or username in seen:
                        continue
                    seen.add(username)

                    bio  = author.get("signature", "") or ""
                    text = item.get("text", "") or ""
                    combined = bio + " " + text

                    temp, reason = _score_text(combined)
                    if temp == 0:
                        continue  # TikTok: only keep warm/hot

                    leads.append({
                        "place_id":          _make_place_id("tiktok", username),
                        "name":              author.get("nickName") or username,
                        "vertical":          vertical,
                        "source":            "signal",
                        "platform":          "tiktok",
                        "phone":             None,
                        "website":           None,
                        "address":           None,
                        "rating":            None,
                        "category":          vertical.replace("_", " ").title(),
                        "lead_temperature":  temp,
                        "temperature_reason": reason,
                        "bio":               bio,
                        "post_text":         text,
                    })

            except Exception as e:
                log.error("tiktok_signal_failed", kw=kw, error=str(e))

    log.info("tiktok_signals", vertical=vertical, found=len(leads))
    return leads[:max_results]


# ── 4. LinkedIn signals (via Apollo hiring/funding events) ───────────────────

async def discover_linkedin_signals(vertical: str, max_results: int = 20) -> list[dict]:
    """
    Detect LinkedIn growth signals via Apollo.io people/company events.
    Flags companies with recent job postings or funding events as hot.
    Requires APOLLO_API_KEY — skipped if missing.
    """
    settings = get_settings()
    apollo_key = getattr(settings, "apollo_api_key", None)
    if not apollo_key:
        return []

    from tools.apollo_discovery import VERTICAL_KEYWORDS
    keywords = VERTICAL_KEYWORDS.get(vertical, [vertical])[:2]
    leads: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20.0) as client:
        for kw in keywords:
            if len(leads) >= max_results:
                break
            try:
                resp = await client.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    headers={"Content-Type": "application/json", "X-Api-Key": apollo_key},
                    json={
                        "q_organization_name": kw,
                        "organization_locations": ["Nigeria"],
                        "page": 1,
                        "per_page": 15,
                        # Filter for companies with recent LinkedIn activity
                        "organization_latest_funding_stage_cd": [],
                    },
                )
                if resp.status_code != 200:
                    continue

                for org in resp.json().get("organizations", []) or []:
                    org_id = str(org.get("id", ""))
                    if not org_id or org_id in seen:
                        continue
                    seen.add(org_id)

                    # Apollo gives us: estimated_num_employees, latest_funding_stage,
                    # num_jobs_10d (jobs posted in last 10 days — key signal)
                    num_jobs_10d  = org.get("num_jobs_10d", 0) or 0
                    funding_stage = org.get("latest_funding_stage") or ""
                    description   = org.get("short_description", "") or ""

                    # Hiring activity in last 10 days = hot signal
                    if num_jobs_10d > 0:
                        temp, reason = 2, f"apollo_{num_jobs_10d}_jobs_10d"
                    elif funding_stage and funding_stage not in ("", "N/A"):
                        temp, reason = 2, f"apollo_funded_{funding_stage}"
                    else:
                        t, r = _score_text(description)
                        temp, reason = (t, r) if t > 0 else (0, None)

                    if temp == 0:
                        continue

                    phone   = org.get("sanitized_phone") or org.get("phone")
                    website = org.get("website_url") or org.get("primary_domain")

                    leads.append({
                        "place_id":          _make_place_id("linkedin", org_id),
                        "name":              org.get("name", ""),
                        "vertical":          vertical,
                        "source":            "signal",
                        "platform":          "linkedin",
                        "phone":             phone,
                        "website":           f"https://{website}" if website and not website.startswith("http") else website,
                        "address":           None,
                        "rating":            None,
                        "category":          vertical.replace("_", " ").title(),
                        "lead_temperature":  temp,
                        "temperature_reason": reason,
                        "bio":               description,
                    })

            except Exception as e:
                log.error("linkedin_signal_failed", kw=kw, error=str(e))

    log.info("linkedin_signals", vertical=vertical, found=len(leads))
    return leads[:max_results]


# ── Unified entry point ───────────────────────────────────────────────────────

async def discover_signal_leads(vertical: str, max_results: int = 60) -> list[dict]:
    """
    Aggregate all signal sources in parallel.
    Returns hot/warm leads sorted by temperature DESC.
    All sources are optional — gracefully no-ops if tokens are missing.
    """
    per_source = max(5, max_results // 4)

    results = await asyncio.gather(
        discover_fb_ads(vertical, per_source),
        discover_twitter_signals(vertical, per_source),
        discover_ig_signals(vertical, per_source),
        discover_tiktok_signals(vertical, per_source),
        discover_linkedin_signals(vertical, per_source),
        return_exceptions=True,
    )

    seen: set[str] = set()
    leads: list[dict] = []
    source_counts: dict[str, int] = {}

    for r in results:
        if isinstance(r, Exception):
            log.error("signal_source_error", error=str(r))
            continue
        for lead in r:
            pid = lead["place_id"]
            if pid not in seen:
                seen.add(pid)
                leads.append(lead)
                plat = lead.get("platform", "unknown")
                source_counts[plat] = source_counts.get(plat, 0) + 1

    # Sort hot first
    leads.sort(key=lambda l: l.get("lead_temperature", 0), reverse=True)

    hot  = sum(1 for l in leads if l.get("lead_temperature") == 2)
    warm = sum(1 for l in leads if l.get("lead_temperature") == 1)
    log.info("signal_intelligence_done", vertical=vertical, total=len(leads),
             hot=hot, warm=warm, sources=source_counts)

    return leads[:max_results]
