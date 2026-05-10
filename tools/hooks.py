"""
Content Intelligence — Hook Generator.
Researches what's performing in a vertical, then generates viral hooks for ANY topic.
Fourth service line for ReachNG: clients pay for hooks that attract inbound.
Outreach (push) + hooks (pull) = complete acquisition stack.
"""
import asyncio
from datetime import datetime, timezone
from database import get_db
from config import get_settings
import structlog

log = structlog.get_logger()


# ── Database ──────────────────────────────────────────────────────────────────

def get_hooks_col():
    return get_db()["hook_library"]


def ensure_hooks_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_hooks_col()
    col.create_index([("client_name", ASCENDING), ("vertical", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])


def save_hooks(client_name: str, vertical: str, topic: str, platform: str, hooks: list[dict]):
    get_hooks_col().insert_one({
        "client_name": client_name,
        "vertical":    vertical,
        "topic":       topic,
        "platform":    platform,
        "hooks":       hooks,
        "created_at":  datetime.now(timezone.utc),
    })


def get_hook_library(client_name: str | None = None, vertical: str | None = None, limit: int = 20) -> list[dict]:
    query = {}
    if client_name:
        query["client_name"] = client_name
    if vertical:
        query["vertical"] = vertical
    return list(get_hooks_col().find(query, {"_id": 0}).sort("created_at", -1).limit(limit))


# ── Trending research via Apify ───────────────────────────────────────────────

async def _fetch_apify(actor_id: str, input_data: dict) -> list[dict]:
    import httpx
    settings = get_settings()
    if not settings.apify_api_token:
        return []
    url    = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": settings.apify_api_token, "timeout": 90, "memory": 256}
    try:
        async with httpx.AsyncClient(timeout=100) as client:
            r = await client.post(url, json=input_data, params=params)
            return r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
    except Exception as e:
        log.error("apify_hooks_failed", error=str(e))
        return []


VERTICAL_HASHTAGS = {
    "real_estate":  ["LagosRealEstate", "LagosProperty", "NigeriaRealEstate"],
    "recruitment":  ["LagosJobs", "NigeriaJobs", "HiringLagos"],
    "events":       ["LagosEvents", "NaijaEvents", "LagosEntertainment"],
    "fintech":      ["LagosFintech", "NigeriaFintech", "AfricanFintech"],
    "legal":        ["LagosLawyer", "NigeriaLaw", "LagosLegal"],
    "logistics":    ["LagosLogistics", "NigeriaLogistics", "FreightLagos"],
    "agriculture":  ["AgribusinessNigeria", "NigeriaFarm", "AgricNigeria"],
}


async def research_trending_hooks(vertical: str, max_posts: int = 30) -> list[str]:
    """
    Scrape top Instagram posts in the vertical, extract first sentences as hook examples.
    These are real hooks that have already earned engagement — not guesses.

    Apify-spend is gated to IG-native verticals only (see tools.apify_gate).
    """
    from tools.apify_gate import should_use_apify_for
    if not should_use_apify_for(vertical):
        return []
    hashtags = VERTICAL_HASHTAGS.get(vertical, [])
    if not hashtags:
        return []

    items = await _fetch_apify("apify/instagram-hashtag-scraper", {
        "hashtags":     hashtags,
        "resultsType":  "posts",
        "resultsLimit": max_posts,
    })

    hooks = []
    for item in items:
        caption = (item.get("caption") or item.get("text", "")).strip()
        if not caption or len(caption) < 20:
            continue
        # Extract first line or first sentence — that's the hook
        first_line = caption.split("\n")[0].strip()
        first_sent = first_line.split(".")[0].strip()
        hook = first_sent if len(first_sent) > 15 else first_line
        if hook and len(hook) < 200:
            hooks.append(hook)

    # Deduplicate and return top examples
    seen = set()
    unique = []
    for h in hooks:
        if h.lower() not in seen:
            seen.add(h.lower())
            unique.append(h)

    log.info("trending_hooks_researched", vertical=vertical, count=len(unique))
    return unique[:20]


async def research_competitor_hooks(competitor_handles: list[str], max_posts: int = 20) -> list[str]:
    """Pull top posts from competitor Instagram accounts and extract their hooks."""
    if not competitor_handles:
        return []

    items = await _fetch_apify("apify/instagram-profile-scraper", {
        "usernames":    competitor_handles,
        "resultsLimit": max_posts,
    })

    hooks = []
    for item in items:
        caption = (item.get("caption") or "").strip()
        if caption and len(caption) > 20:
            first_line = caption.split("\n")[0].strip()
            if first_line and len(first_line) < 200:
                hooks.append(first_line)

    return list(set(hooks))[:15]


# ── Claude hook generation ────────────────────────────────────────────────────

def generate_hooks(
    vertical: str,
    topic: str,
    platform: str,
    count: int = 8,
    trending_examples: list[str] | None = None,
    competitor_examples: list[str] | None = None,
    client_brief: str | None = None,
) -> list[dict]:
    """
    Generate viral hooks for a given topic using Claude Sonnet.
    Uses real trending examples as style reference — not generic outputs.
    Returns list of {hook, format, why_it_works}.
    """
    import anthropic, json
    settings = get_settings()
    client   = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    platform_guidance = {
        "instagram": "Instagram captions — hook must stop the scroll in the first line. 5–12 words ideal.",
        "twitter":   "Twitter/X — hook is the whole first tweet. Under 280 chars, punchy, strong POV.",
        "linkedin":  "LinkedIn — hook is the first 2 lines before 'See more'. Professional but bold.",
        "whatsapp":  "WhatsApp broadcast — first sentence before someone ignores. Conversational, local.",
    }.get(platform, "social media post — first sentence must grab attention immediately.")

    trending_block = ""
    if trending_examples:
        trending_block = "\n\nTRENDING HOOKS IN THIS NICHE (these already earned engagement — use as style reference):\n" + \
            "\n".join(f"• {h}" for h in trending_examples[:10])

    competitor_block = ""
    if competitor_examples:
        competitor_block = "\n\nCOMPETITOR HOOKS (study what they're doing, then do better):\n" + \
            "\n".join(f"• {h}" for h in competitor_examples[:8])

    client_block = f"\n\nCLIENT CONTEXT:\n{client_brief}" if client_brief else ""

    prompt = f"""You are an expert content strategist who writes viral hooks for Lagos businesses.

TASK: Generate {count} viral hooks for the following.

Vertical: {vertical.replace('_', ' ').title()}
Topic: {topic}
Platform: {platform} ({platform_guidance})
{trending_block}{competitor_block}{client_block}

HOOK FORMATS TO VARY ACROSS THE {count} HOOKS:
1. Bold claim — "Most Lagos [X] are making this mistake"
2. Curiosity gap — "What nobody tells you about [X] in Lagos"
3. Specific number — "3 reasons Lagos [X] fail in year one"
4. Story opener — "I spent ₦2M on [X] so you don't have to"
5. Contrarian — "Unpopular opinion: [conventional wisdom] is wrong"
6. Direct address — "If you're a Lagos [X], read this"
7. Question — "Are you making this [X] mistake?"
8. Result first — "How we got [X result] in [short time]"

Return ONLY a JSON array of {count} objects, each with:
- "hook": the hook text
- "format": which format type (bold_claim, curiosity_gap, etc.)
- "why_it_works": one sentence explanation

No preamble. JSON only.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        hooks = json.loads(raw.strip())
        return hooks if isinstance(hooks, list) else []
    except Exception:
        log.warning("hooks_parse_failed", raw=raw[:200])
        # Fallback: return raw lines as simple hooks
        return [{"hook": line.strip("•- "), "format": "unknown", "why_it_works": ""}
                for line in raw.split("\n") if line.strip() and len(line.strip()) > 10]


# ── Full pipeline: research + generate ───────────────────────────────────────

async def generate_hooks_with_research(
    vertical: str,
    topic: str,
    platform: str = "instagram",
    count: int = 8,
    competitor_handles: list[str] | None = None,
    client_brief: str | None = None,
    client_name: str = "default",
) -> dict:
    """
    Full pipeline: research trending hooks → research competitors → generate.
    Returns hooks + the trending examples used as reference.
    """
    # Research in parallel
    tasks = [research_trending_hooks(vertical, max_posts=30)]
    if competitor_handles:
        tasks.append(research_competitor_hooks(competitor_handles, max_posts=20))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    trending    = results[0] if not isinstance(results[0], Exception) else []
    competitors = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else []

    hooks = generate_hooks(
        vertical=vertical,
        topic=topic,
        platform=platform,
        count=count,
        trending_examples=trending,
        competitor_examples=competitors,
        client_brief=client_brief,
    )

    # Persist to library
    save_hooks(client_name, vertical, topic, platform, hooks)

    return {
        "hooks":              hooks,
        "trending_reference": trending[:5],
        "competitor_reference": competitors[:5],
        "topic":              topic,
        "vertical":           vertical,
        "platform":           platform,
        "count":              len(hooks),
    }
