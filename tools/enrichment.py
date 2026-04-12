"""
Deep Personalization Engine — crawl a business website before Claude writes outreach.

Fetches the homepage + /about page, extracts:
  - Business description / about blurb
  - Services offered
  - Team names (founder/CEO if visible)
  - Recent news or taglines

Result is fed into the Claude prompt so messages reference real details,
not just the business name and Google Maps category.

No Instagram scraping — website crawling only (legal, reliable).
Uses httpx with a 10s timeout. Falls back gracefully if site is unreachable.
"""
import asyncio
import re
import ipaddress
import socket
import httpx
import structlog
from typing import Optional
from urllib.parse import urljoin, urlparse

log = structlog.get_logger()

_TIMEOUT = 10.0
_MAX_BYTES = 80_000   # ~80 KB — enough for any homepage, avoids huge pages
_USER_AGENT = "Mozilla/5.0 (compatible; ReachNG/1.0; outreach-bot)"


# ─── Public interface ─────────────────────────────────────────────────────────

async def enrich_business(website: Optional[str], business_name: str) -> dict:
    """
    Crawl the business website and return a dict with enrichment context.

    Returns:
        {
            "description": str | None,
            "services": list[str],
            "team_names": list[str],
            "tagline": str | None,
            "email": str | None,   # extracted from website contact page / footer
            "enriched": bool,      # False if crawl failed or no website
        }
    """
    empty = {"description": None, "services": [], "team_names": [], "tagline": None, "email": None, "enriched": False}

    if not website:
        return empty

    url = _normalise_url(website)
    if not url:
        return empty

    try:
        # Fetch homepage + /about + /contact concurrently for maximum email coverage
        homepage_task = _fetch(url)
        about_task    = _fetch(urljoin(url, "/about"))
        contact_task  = _fetch(urljoin(url, "/contact"))

        html, about_html, contact_html = await asyncio.gather(
            homepage_task, about_task, contact_task, return_exceptions=True
        )
        html         = html         if isinstance(html, str)         else ""
        about_html   = about_html   if isinstance(about_html, str)   else ""
        contact_html = contact_html if isinstance(contact_html, str) else ""

        if not html:
            return empty

        combined = html + " " + about_html + " " + contact_html
        text = _strip_html(combined)

        result = {
            "description": _extract_description(text, business_name),
            "services":    _extract_services(text),
            "team_names":  _extract_team_names(text),
            "tagline":     _extract_tagline(html),
            "email":       _extract_email(combined),
            "enriched":    True,
        }
        log.info("enrichment_done", business=business_name,
                 services=len(result["services"]), team=len(result["team_names"]),
                 email_found=bool(result["email"]))
        return result

    except Exception as exc:
        log.warning("enrichment_failed", business=business_name, url=url, error=str(exc))
        return empty


def format_enrichment_for_prompt(enrichment: dict, business_name: str) -> str:
    """
    Format enrichment data as a compact context block for Claude prompts.
    Returns empty string if enrichment failed.
    """
    if not enrichment.get("enriched"):
        return ""

    parts = []

    if enrichment.get("tagline"):
        parts.append(f"Tagline: {enrichment['tagline']}")

    if enrichment.get("description"):
        parts.append(f"About: {enrichment['description'][:300]}")

    if enrichment.get("services"):
        services = ", ".join(enrichment["services"][:5])
        parts.append(f"Services: {services}")

    if enrichment.get("team_names"):
        names = ", ".join(enrichment["team_names"][:3])
        parts.append(f"Team/founders visible on site: {names}")

    if not parts:
        return ""

    return "Website intelligence:\n" + "\n".join(f"  - {p}" for p in parts)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _normalise_url(website: str) -> Optional[str]:
    """Ensure URL has a scheme and is safe to fetch (no SSRF)."""
    website = website.strip()
    if not website:
        return None
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    parsed = urlparse(website)
    if not parsed.netloc:
        return None
    if not _is_safe_host(parsed.hostname or ""):
        log.warning("enrichment_ssrf_blocked", url=website)
        return None
    return website


def _is_safe_host(host: str) -> bool:
    """Block private/internal IPs and localhost to prevent SSRF."""
    if not host:
        return False
    # Block obvious hostnames
    blocked_hosts = {"localhost", "metadata.google.internal"}
    if host.lower() in blocked_hosts:
        return False
    # Resolve hostname to IP and check if it's public
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global and not ip.is_private and not ip.is_loopback and not ip.is_link_local
    except ValueError:
        # It's a domain name — resolve and check
        try:
            resolved = socket.getaddrinfo(host, None)
            for item in resolved:
                ip = ipaddress.ip_address(item[4][0])
                if not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False
        except Exception:
            return False
    return True


async def _fetch(url: str) -> Optional[str]:
    """Fetch URL asynchronously, return text or None. Respects size limit."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            content = resp.content[:_MAX_BYTES]
            return content.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_tagline(html: str) -> Optional[str]:
    """Extract meta description or og:description — usually the tagline."""
    patterns = [
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+content=["\'](.*?)["\']\s+name=["\']description["\']',
        r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if 20 < len(val) < 300:
                return val
    return None


def _extract_description(text: str, business_name: str) -> Optional[str]:
    """Find sentences that look like an about/description."""
    # Look for sentences near "about us", "who we are", "we are", "our mission"
    about_pattern = re.compile(
        r"(?:about us|who we are|our mission|we are|we provide|we offer|our company)[^.]{0,20}([^.]{40,300}\.)",
        re.IGNORECASE
    )
    m = about_pattern.search(text)
    if m:
        return m.group(1).strip()

    # Fallback: first long sentence that mentions the business name or "we"
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        if len(sent) > 60 and ("we " in sent.lower() or business_name.lower()[:6] in sent.lower()):
            return sent.strip()[:300]

    return None


def _extract_services(text: str) -> list[str]:
    """Extract a list of services from text."""
    services = []

    # Look for a services/offerings section
    services_block = re.search(
        r"(?:our services|what we offer|what we do|services)[:\s]+((?:[A-Z][^.!?\n]{5,60}[.!?\n]?\s*){1,8})",
        text, re.IGNORECASE
    )
    if services_block:
        block = services_block.group(1)
        # Split on newlines, bullets, or sentence ends
        items = re.split(r"[\n•·▪▸\-–—]|\d+\.\s", block)
        for item in items:
            item = item.strip().rstrip(".")
            if 5 < len(item) < 80:
                services.append(item)
            if len(services) >= 6:
                break

    return services


def _extract_email(html: str) -> Optional[str]:
    """Extract the first business email found in the page source."""
    # Common mailto links first — most reliable
    mailto = re.search(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    if mailto:
        return mailto.group(1).lower()
    # Plain email pattern in text
    match = re.search(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b', html)
    if match:
        email = match.group(1).lower()
        # Skip common false positives
        skip = {"example.com", "domain.com", "yourdomain.com", "email.com",
                "sentry.io", "w3.org", "schema.org"}
        if not any(s in email for s in skip):
            return email
    return None


def _extract_team_names(text: str) -> list[str]:
    """Extract names that appear near founder/CEO/director/team role titles."""
    # Match "John Smith, CEO" or "CEO: John Smith" patterns
    patterns = [
        r"([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)[,\s]+(?:CEO|Founder|Co-Founder|Director|MD|Owner|Manager|Head)",
        r"(?:CEO|Founder|Co-Founder|Director|MD|Owner)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
    ]
    names = []
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            if name not in seen and len(name.split()) >= 2:
                names.append(name)
                seen.add(name)
            if len(names) >= 4:
                break
    return names
