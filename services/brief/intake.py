"""
AI-assisted Business Brief intake.

Flow:
  1. Client gives us source material — their website URL, brochure text, IG bio,
     a free-text "describe your business" answer, or any combination.
  2. We fetch the URL (if provided), strip to readable text.
  3. Claude Haiku reads everything + the vertical primer and emits a structured
     BusinessBrief draft in JSON.
  4. The caller stores it as `intake_source="ai_assisted"` for the client to review,
     edit, and save.

This is intake — not autopilot. The client always reviews + saves explicitly.
"""
from __future__ import annotations

import json
import re
import structlog
from typing import Optional

from services.brief.store import BusinessBrief, get_primer
from config import get_settings

log = structlog.get_logger()

_MAX_FETCH_BYTES = 800_000          # don't pull more than ~800KB of HTML
_MAX_TEXT_CHARS  = 18_000           # what we feed Claude (Haiku context safe)


async def assist_intake(
    *,
    vertical: str,
    url: Optional[str] = None,
    free_text: Optional[str] = None,
    questions_answers: Optional[dict[str, str]] = None,
) -> dict:
    """Build a BusinessBrief draft from the source material the client supplied.

    Returns: {"brief": <BusinessBrief dict>, "warnings": [...], "source_chars": int}
    """
    if not (url or free_text or questions_answers):
        raise ValueError("Provide at least one of: url, free_text, questions_answers")

    warnings: list[str] = []
    source_text_parts: list[str] = []

    if url:
        try:
            fetched = await _fetch_url_text(url)
            if fetched:
                source_text_parts.append(f"### From {url}\n{fetched}")
            else:
                warnings.append(f"Could not extract readable text from {url}")
        except Exception as e:
            warnings.append(f"Could not fetch {url}: {e}")

    if free_text:
        source_text_parts.append(f"### Owner-supplied description\n{free_text.strip()}")

    if questions_answers:
        qa_lines = [f"Q: {q}\nA: {a}" for q, a in questions_answers.items() if a and a.strip()]
        if qa_lines:
            source_text_parts.append("### Owner Q&A\n" + "\n\n".join(qa_lines))

    source_text = "\n\n".join(source_text_parts)[:_MAX_TEXT_CHARS]
    if not source_text:
        return {"brief": BusinessBrief().model_dump(), "warnings": warnings + ["No source text available"], "source_chars": 0}

    primer = get_primer(vertical) or {}
    brief = await _claude_structure(vertical=vertical, primer=primer, source_text=source_text)
    brief["intake_source"] = "ai_assisted"

    return {
        "brief": brief,
        "warnings": warnings,
        "source_chars": len(source_text),
    }


# ─── URL fetching ────────────────────────────────────────────────────────────

async def _fetch_url_text(url: str) -> str:
    """Fetch a URL and return clean text — with SSRF guards.

    Rejects:
      - non-http(s) schemes (file://, ftp://, gopher://, data:, etc.)
      - private/loopback/link-local/multicast IPs (resolved before connect)
      - cloud metadata endpoints (169.254.169.254 — AWS/GCP/Azure)
      - unresolvable hostnames

    Limits:
      - 15s total timeout
      - 2 redirects max (each re-validated)
      - 800KB body cap
      - text/html or text/plain only
    """
    import socket
    import ipaddress
    from urllib.parse import urlparse
    import httpx

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http(s) URLs allowed, got '{parsed.scheme}'")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must include a hostname")

    # Resolve and reject private/loopback/link-local/multicast.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve '{host}': {e}")
    for fam, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError(f"Refused to fetch '{host}' — resolves to non-public IP {ip_str}")

    headers = {
        "User-Agent": "ReachNG-BriefIntake/1.0 (+https://reachng.ng)",
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.8",
    }
    # follow_redirects=False so we manually re-validate each hop's destination.
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        current_url = url
        for _ in range(3):  # initial + 2 redirects
            r = await client.get(current_url, headers=headers)
            if r.is_redirect:
                next_url = r.headers.get("location") or ""
                if not next_url:
                    break
                # Re-validate the redirect target — rebinding-safe.
                next_parsed = urlparse(next_url)
                if next_parsed.scheme not in ("http", "https"):
                    raise ValueError(f"Refused redirect to scheme '{next_parsed.scheme}'")
                next_host = next_parsed.hostname or host
                try:
                    next_infos = socket.getaddrinfo(next_host, None)
                except socket.gaierror:
                    raise ValueError(f"Cannot resolve redirect target '{next_host}'")
                for _f, _t, _p, _c, sa in next_infos:
                    ip = ipaddress.ip_address(sa[0])
                    if (ip.is_private or ip.is_loopback or ip.is_link_local
                            or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                        raise ValueError(f"Refused redirect to non-public IP {sa[0]}")
                current_url = next_url
                continue
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "text/html" not in ctype and "text/plain" not in ctype:
                return ""
            body = r.content[:_MAX_FETCH_BYTES]
            return _html_to_text(body.decode(r.encoding or "utf-8", errors="ignore"))
    return ""


def _html_to_text(html: str) -> str:
    """Strip script/style, collapse whitespace. Simple and dependency-free."""
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"&#39;", "'", html)
    html = re.sub(r"&quot;", '"', html)
    return re.sub(r"\s+", " ", html).strip()


# ─── Claude structuring ──────────────────────────────────────────────────────

async def _claude_structure(*, vertical: str, primer: dict, source_text: str) -> dict:
    """Ask Claude Haiku to extract a BusinessBrief from raw source material."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    schema_hint = json.dumps(BusinessBrief().model_dump(), indent=2)
    primer_label = primer.get("label") or vertical
    primer_one_liner = primer.get("sample_one_liner") or ""

    prompt = (
        f"You are extracting a structured business brief for a {primer_label} company in Nigeria. "
        f"Read the source material and fill the JSON schema below.\n\n"
        f"Rules:\n"
        f"- Only fill fields you have clear evidence for. Leave others as their default empty value.\n"
        f"- Never invent products, prices, claims, or social proof. If unclear, leave blank.\n"
        f"- For `tone_overrides`, only set if the source explicitly suggests a tone different from default.\n"
        f"- For `never_say`, infer 2-4 entries from the source (things they would clearly never want to say).\n"
        f"- For `signature`, use the trading name preceded by '— ' if you can identify the trading name.\n"
        f"- Keep `one_liner` under 20 words.\n"
        f"- Output ONLY valid JSON matching the schema. No prose, no code fences.\n\n"
        f"Schema (defaults shown — replace with real values where confident):\n{schema_hint}\n\n"
        f"Reference (sample one-liner for this vertical, do NOT copy verbatim): {primer_one_liner}\n\n"
        f"SOURCE MATERIAL:\n{source_text}"
    )

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (msg.content[0].text or "").strip()
    raw = _strip_code_fence(raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("brief_intake_parse_failed", preview=raw[:200])
        return BusinessBrief().model_dump()

    # Coerce through the model so unknown keys are dropped and defaults fill gaps.
    try:
        coerced = BusinessBrief(**{k: v for k, v in parsed.items() if k in BusinessBrief.model_fields})
        return coerced.model_dump()
    except Exception as e:
        log.warning("brief_intake_coerce_failed", error=str(e))
        return BusinessBrief().model_dump()


def _strip_code_fence(text: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ``` despite instructions. Strip it."""
    text = text.strip()
    if text.startswith("```"):
        # remove first fence line and trailing fence
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()
