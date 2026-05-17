"""
Lean Scraper — proprietary internal scraping engine.

PROPRIETARY · INTERNAL USE ONLY · DO NOT EXTRACT FOR OSS RELEASE.

Why this exists
---------------
Apify, ScrapeGraphAI, and every browser-based scraping tool charge per-actor-
minute or require 300MB of Playwright/Chromium that won't deploy clean on
Railway. For Lagos SME discovery + enrichment we don't need any of that — we
need: DuckDuckGo for search, httpx for fetching, and Claude Haiku for
structured extraction. That's the entire stack.

This module is the internal engine that powers ReachNG's discovery + enrichment
pipelines without paying Apify a kobo. It is NOT published anywhere. The moat
is:
  1. Cost — every scrape is ~₦4 in API spend vs ~₦40-100 on Apify per actor run.
  2. Speed — no browser warmup. Parallel scrape natively, gather-style.
  3. Margin — when a client signs up at ₦150K/month, we keep more of it.
  4. Optionality — if we ever spin this out as a standalone product, we own it.

Public API (internal only)
--------------------------
    await scrape(url, schema, hint=None) -> dict
    await search(query, max_results=10)  -> list[SearchResult]
    await discover(query, schema, max_results=5, hint=None) -> list[dict]

Notes
-----
- Schema is a Pydantic BaseModel class. The extractor produces an instance of
  it (parsed dict) so callers get type-safe, validated output.
- `hint` is an optional free-text instruction passed to the extractor
  ("focus on contact emails and decision-maker names", "extract pricing tiers
  if visible").
- All retries + timeouts handled internally. Failures return None / empty —
  never raise. Caller decides fallback.
- No PyPI metadata. No license header. No __version__. This file is not for
  distribution.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional, Type, Any
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from config import get_settings

log = structlog.get_logger()


# ─── Tuneables ────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = 12.0          # seconds per page fetch
MAX_HTML_BYTES = 600_000     # truncate huge pages before sending to Haiku
PARALLEL_SCRAPES = 6         # concurrent scrapes inside discover()
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_MAX_TOKENS = 800

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    title:   str
    url:     str
    snippet: str
    source:  str = "ddg"      # in case we add other backends later


# ─── HTML fetch ──────────────────────────────────────────────────────────────

async def _fetch(url: str) -> Optional[str]:
    """Fetch a URL with a real browser UA. Returns text or None on failure."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"},
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            ct = (r.headers.get("content-type") or "").lower()
            if "html" not in ct and "text" not in ct:
                return None
            return r.text[:MAX_HTML_BYTES]
    except Exception as e:
        log.info("lean_fetch_failed", url=url, error=str(e))
        return None


# ─── HTML → clean text ───────────────────────────────────────────────────────

_TAG_DROP_RE = re.compile(r"<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> str:
    """Strip tags + collapse whitespace. Light, no BS4 dependency."""
    if not html:
        return ""
    html = _TAG_DROP_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


# ─── DuckDuckGo search ───────────────────────────────────────────────────────

def _ddg_sync(query: str, max_results: int) -> list[SearchResult]:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        log.warning("lean_ddg_missing", note="pip install duckduckgo-search")
        return []
    out: list[SearchResult] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, region="ng-en"):
                out.append(SearchResult(
                    title=(r.get("title") or "").strip(),
                    url=(r.get("href") or r.get("url") or "").strip(),
                    snippet=(r.get("body") or "").strip(),
                ))
    except Exception as e:
        log.warning("lean_ddg_failed", error=str(e))
    return out


async def search(query: str, max_results: int = 10) -> list[SearchResult]:
    """DuckDuckGo search (NG region). Returns up to max_results."""
    if not query or not query.strip():
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ddg_sync, query.strip(), max_results)


# ─── Haiku structured extraction ─────────────────────────────────────────────

def _schema_description(schema: Type[BaseModel]) -> str:
    """Produce a short JSON-schema description Haiku can follow."""
    fields = []
    for name, field in schema.model_fields.items():
        annot = field.annotation
        type_name = getattr(annot, "__name__", str(annot))
        # Optional/Union flattening for readability
        type_name = type_name.replace("Optional", "").replace("Union", "").strip("[] ")
        desc = field.description or ""
        fields.append(f'  "{name}": <{type_name}>' + (f"  // {desc}" if desc else ""))
    return "{\n" + ",\n".join(fields) + "\n}"


async def _haiku_extract(
    text: str,
    schema: Type[BaseModel],
    hint: Optional[str],
    url: Optional[str],
) -> Optional[dict]:
    """Single Haiku call: page text -> JSON matching schema. Returns dict or None."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception:
        return None

    schema_desc = _schema_description(schema)
    hint_block = f"\n\nFOCUS HINT: {hint}" if hint else ""
    url_block = f"\n\nSOURCE URL: {url}" if url else ""

    system = (
        "You are a structured-data extractor. Given the cleaned text content of "
        "a web page, return ONLY a JSON object matching the requested schema. "
        "If a field is not present on the page, set it to null or an empty array. "
        "Do not invent data. Do not include any prose or markdown — JSON only."
    )
    user = (
        f"Extract the following fields from the page text below.\n\n"
        f"SCHEMA:\n{schema_desc}{url_block}{hint_block}\n\n"
        f"PAGE TEXT (truncated):\n{text[:18_000]}"
    )

    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=HAIKU_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ))
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        log.warning("lean_haiku_failed", error=str(e))
        return None

    # Tolerant JSON extraction
    if raw.startswith("```"):
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        else:
            return None
    try:
        data = json.loads(raw)
    except Exception:
        log.info("lean_json_parse_failed", head=raw[:120])
        return None

    # Validate against schema (drop fields the schema doesn't define)
    try:
        validated = schema.model_validate(data)
        return validated.model_dump()
    except ValidationError as e:
        log.info("lean_schema_violation", error=str(e)[:200])
        # Return raw dict anyway — caller may still find it useful
        return data


# ─── Public: scrape single URL ───────────────────────────────────────────────

async def scrape(
    url: str,
    schema: Type[BaseModel],
    hint: Optional[str] = None,
) -> Optional[dict]:
    """Fetch a page, extract structured data via Haiku. None on failure.

    Example:
        class BizContact(BaseModel):
            business_name: Optional[str] = None
            phone: Optional[str] = None
            email: Optional[str] = None
            decision_maker: Optional[str] = None

        data = await scrape("https://lagosrestaurant.com", BizContact,
                            hint="focus on owner contact + booking phone")
    """
    html = await _fetch(url)
    if not html:
        return None
    text = _html_to_text(html)
    if len(text) < 100:
        return None
    return await _haiku_extract(text, schema, hint, url)


# ─── Public: discover (search + scrape + extract) ────────────────────────────

async def discover(
    query: str,
    schema: Type[BaseModel],
    max_results: int = 5,
    hint: Optional[str] = None,
) -> list[dict]:
    """Search DuckDuckGo for `query`, scrape the top N results, extract structured
    data into `schema`. Returns list of dicts (possibly shorter than max_results
    if some fetches/extractions fail).

    Example:
        class RestaurantLead(BaseModel):
            name: Optional[str]
            phone: Optional[str]
            instagram: Optional[str]
            address: Optional[str]

        leads = await discover(
            "fine dining victoria island lagos",
            RestaurantLead,
            max_results=10,
            hint="extract restaurant name, contact phone, IG handle, address"
        )
    """
    results = await search(query, max_results=max_results)
    if not results:
        return []

    # Filter junk before scraping
    candidates = [r for r in results if _is_business_url(r.url)]
    if not candidates:
        return []

    # Limit parallelism to avoid blowing the event loop / Haiku rate limit
    sem = asyncio.Semaphore(PARALLEL_SCRAPES)

    async def _one(result: SearchResult) -> Optional[dict]:
        async with sem:
            data = await scrape(result.url, schema, hint=hint)
            if data:
                data["_source_url"] = result.url
                data["_source_title"] = result.title
            return data

    out = await asyncio.gather(*[_one(r) for r in candidates], return_exceptions=False)
    return [d for d in out if d]


def _is_business_url(url: str) -> bool:
    """Filter out junk: directories, social aggregators, news, etc."""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    junk = (
        "facebook.com", "twitter.com", "x.com", "linkedin.com",
        "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
        "wikipedia.org", "yelp.com", "tripadvisor.com",
        "yellowpages.", "businesslist.", "vconnect.com", "finelibng.",
        "punchng.com", "bellanaija.com", "guardian.ng",   # news
        "reddit.com", "quora.com",
    )
    return not any(j in host for j in junk)
