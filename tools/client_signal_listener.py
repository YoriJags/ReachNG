"""
Client Signal Listener — finds people who are ALREADY looking for what a client sells.

This is NOT the internal SDR funnel (that finds businesses to pitch ReachNG to).
This monitors social/web for CUSTOMER intent signals on behalf of a paying client,
then surfaces them as warm leads in a separate "Signal Leads" queue.

Client must explicitly enable this (signal_listening: True on their record).
Every signal card clearly states: "ReachNG found this — they haven't contacted you yet."

Sources (all DDG-based, no API keys required):
  1. Twitter/X — intent phrases like "looking for rooftop bar VI"
  2. Facebook/community groups — recommendation requests
  3. Generic web — forum posts, blog comments, listing sites

Per-vertical intent queries target BUYERS, not businesses.
"""
import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
import structlog
from database import get_db
from bson import ObjectId

log = structlog.get_logger()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ReachNG/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Per-vertical BUYER intent queries ─────────────────────────────────────────
# These surface people who are ALREADY looking for what the client sells.
# Deliberately different from signal_intelligence.py (which finds businesses to pitch ReachNG to).

BUYER_INTENT_QUERIES: dict[str, list[str]] = {
    "hospitality": [
        "site:twitter.com looking for rooftop bar Lagos",
        "site:twitter.com birthday venue Lagos island recommendation",
        "site:twitter.com private event venue VI Lagos",
        "site:twitter.com where to celebrate Lagos lounge",
        "site:twitter.com table reservation rooftop Lagos",
        "Lagos lounge recommendation birthday private hire",
        "site:twitter.com Lagos bar reservation this weekend",
    ],
    "small_business": [
        "site:twitter.com looking for fashion Lagos DM order",
        "site:twitter.com anyone know good baker Lagos custom cake",
        "site:twitter.com Lagos tailor recommendation bespoke",
        "site:twitter.com skincare brand Lagos recommendation",
        "site:twitter.com where to buy Lagos interior decor",
        "Lagos small business recommendation need vendor",
    ],
    "real_estate": [
        "site:twitter.com looking for apartment Lagos island 2 bedroom",
        "site:twitter.com flat to rent Lekki VI Ikoyi",
        "site:twitter.com property for sale Lagos recommendation",
        "site:twitter.com need realtor Lagos trustworthy",
        "site:twitter.com short let Lagos island available",
    ],
    "events": [
        "site:twitter.com event planner Lagos recommendation",
        "site:twitter.com corporate event Lagos vendor needed",
        "site:twitter.com concert Lagos ticket available",
        "site:twitter.com brand activation Lagos vendor",
    ],
    "recruitment": [
        "site:twitter.com hiring Lagos recommendation recruiter",
        "site:twitter.com HR firm Lagos reliable",
        "site:twitter.com payroll company Nigeria recommendation",
    ],
    "logistics": [
        "site:twitter.com logistics company Lagos recommendation",
        "site:twitter.com haulage Lagos reliable",
        "site:twitter.com last mile delivery Lagos",
    ],
}

# Platform label for display
_PLATFORM_LABELS = {
    "twitter": "Twitter/X",
    "facebook": "Facebook",
    "web": "Web",
}


# ── Mongo collection ───────────────────────────────────────────────────────────

def get_signal_queue():
    return get_db()["client_signal_queue"]


def ensure_signal_indexes():
    from pymongo import ASCENDING, DESCENDING
    col = get_signal_queue()
    col.create_index([("client_name", ASCENDING), ("status", ASCENDING)])
    col.create_index([("signal_id", ASCENDING)], unique=True)
    col.create_index([("found_at", DESCENDING)])


def _is_seen(signal_id: str) -> bool:
    return get_signal_queue().count_documents({"signal_id": signal_id}) > 0


# ── DDG search ────────────────────────────────────────────────────────────────

def _ddg_sync(query: str, max_results: int = 8) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results)) or []
    except Exception as e:
        log.error("signal_ddg_failed", error=str(e))
        return []


_TW_HANDLE_RE = re.compile(r"twitter\.com/([A-Za-z0-9_]+)(?:/|$)")
_PHONE_RE     = re.compile(r"(\+?234[789]\d{9}|0[789]\d{9})")


def _parse_twitter_result(r: dict) -> Optional[dict]:
    url     = r.get("href", "")
    snippet = r.get("body", "") or r.get("description", "")
    title   = r.get("title", "")

    m = _TW_HANDLE_RE.search(url)
    if not m:
        return None
    handle = m.group(1)
    if handle.lower() in {"search", "hashtag", "i", "home", "explore", "notifications", "intent"}:
        return None

    combined = f"{title} {snippet}"
    phone_m  = _PHONE_RE.search(combined)

    return {
        "platform":    "twitter",
        "handle":      handle,
        "display_name": title.split("(")[0].split("·")[0].strip() or handle,
        "post_text":   snippet[:400],
        "profile_url": f"https://twitter.com/{handle}",
        "phone":       phone_m.group(0) if phone_m else None,
        "signal_id":   f"csig_tw_{handle}_{hash(snippet[:50]) & 0xffffffff:x}",
    }


def _parse_web_result(r: dict) -> Optional[dict]:
    url     = r.get("href", "")
    snippet = r.get("body", "") or ""
    title   = r.get("title", "")
    if not snippet or len(snippet) < 30:
        return None
    return {
        "platform":    "web",
        "handle":      url,
        "display_name": title[:60],
        "post_text":   snippet[:400],
        "profile_url": url,
        "phone":       None,
        "signal_id":   f"csig_web_{hash(url) & 0xffffffff:x}",
    }


# ── Main listener ─────────────────────────────────────────────────────────────

async def run_client_signal_listener(
    client_name: str,
    vertical: str,
    max_signals: int = 15,
    extra_queries: list[str] | None = None,
) -> dict:
    """
    Run signal search for one client and store results in client_signal_queue.
    Returns summary dict.

    extra_queries: client-specific search terms (e.g. "looking for Mercury Lagos rooftop")
    """
    base_queries = BUYER_INTENT_QUERIES.get(vertical, [])
    all_queries  = base_queries[:5]

    # Always include client-name specific queries if provided
    if extra_queries:
        all_queries = extra_queries[:3] + all_queries

    if not all_queries:
        return {"found": 0, "new": 0, "vertical": vertical}

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _ddg_sync, q, 8)
        for q in all_queries[:6]
    ]
    all_raw = await asyncio.gather(*tasks, return_exceptions=True)

    new_signals = 0
    for batch in all_raw:
        if isinstance(batch, Exception) or new_signals >= max_signals:
            continue
        for r in batch:
            url = r.get("href", "")
            parsed = (
                _parse_twitter_result(r) if "twitter.com" in url
                else _parse_web_result(r)
            )
            if not parsed:
                continue
            if _is_seen(parsed["signal_id"]):
                continue

            try:
                get_signal_queue().insert_one({
                    **parsed,
                    "client_name": client_name,
                    "vertical":    vertical,
                    "status":      "pending",      # pending | drafted | skipped
                    "found_at":    datetime.now(timezone.utc),
                    "draft_id":    None,            # set when draft is generated
                })
                new_signals += 1
            except Exception:
                pass  # duplicate signal_id race condition

    log.info("client_signal_listener_done", client=client_name, vertical=vertical, new=new_signals)
    return {"found": len(all_raw), "new": new_signals, "vertical": vertical}


async def run_all_client_listeners() -> dict:
    """Called by scheduler — runs signal listener for every client with signal_listening=True."""
    from api.clients import get_clients
    clients = list(get_clients().find(
        {"active": True, "signal_listening": True},
        {"name": 1, "vertical": 1, "signal_queries": 1},
    ))

    total_new = 0
    for c in clients:
        try:
            result = await run_client_signal_listener(
                client_name=c["name"],
                vertical=c.get("vertical", "hospitality"),
                extra_queries=c.get("signal_queries") or [],
            )
            total_new += result.get("new", 0)
        except Exception as e:
            log.error("client_listener_error", client=c["name"], error=str(e))

    log.info("all_client_listeners_done", total_new=total_new, clients=len(clients))
    return {"total_new": total_new, "clients_run": len(clients)}


# ── Signal queue reads ─────────────────────────────────────────────────────────

def get_pending_signals(client_name: str, limit: int = 20) -> list[dict]:
    """Return pending signal leads for one client."""
    signals = list(
        get_signal_queue()
        .find({"client_name": client_name, "status": "pending"})
        .sort("found_at", -1)
        .limit(limit)
    )
    for s in signals:
        s["id"] = str(s.pop("_id"))
        if hasattr(s.get("found_at"), "isoformat"):
            s["found_at"] = s["found_at"].isoformat()
    return signals


def skip_signal(signal_id_str: str) -> bool:
    result = get_signal_queue().update_one(
        {"_id": ObjectId(signal_id_str)},
        {"$set": {"status": "skipped"}},
    )
    return result.matched_count > 0


def mark_signal_drafted(signal_id_str: str, draft_id: str):
    get_signal_queue().update_one(
        {"_id": ObjectId(signal_id_str)},
        {"$set": {"status": "drafted", "draft_id": draft_id}},
    )
