"""
Public blog (SPRINT 3 — content engine seed).

Renders Markdown posts from `content/blog/*.md` with frontmatter:

    ---
    title: "Why premium Lagos owners stopped trying to use AI"
    slug: why-lagos-owners-stopped-trying-ai
    date: 2026-05-22
    description: "Short summary used for OG + index card."
    author: "Yori Ajagun"
    vertical: hospitality  # optional, drives a sidebar nudge
    ---

    # The post body in Markdown...

Routes:
  GET /blog              -> index (latest first)
  GET /blog/{slug}       -> one post

SEO: each post emits Article + BreadcrumbList JSON-LD via the template.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

log = structlog.get_logger()
router = APIRouter(tags=["Blog"])

_ROOT = Path(__file__).resolve().parent.parent
_POSTS_DIR = _ROOT / "content" / "blog"

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Lightweight YAML-ish parser — handles key: value lines only.
    Avoids the PyYAML dependency for this small surface."""
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw
    meta_block, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in meta_block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        meta[k.strip()] = v
    return meta, body


def _load_post(slug: str) -> Optional[dict]:
    path = _POSTS_DIR / f"{slug}.md"
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, body = _parse_frontmatter(raw)
    if not meta.get("slug"):
        meta["slug"] = slug
    try:
        import markdown as _md
        html = _md.markdown(body, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    except Exception:
        html = f"<pre>{body}</pre>"
    return {"meta": meta, "html": html, "raw": body}


def _list_posts() -> list[dict]:
    """Returns post metadata sorted by date desc. Body NOT loaded."""
    if not _POSTS_DIR.exists():
        return []
    posts = []
    for path in _POSTS_DIR.glob("*.md"):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, _ = _parse_frontmatter(raw)
        if not meta:
            continue
        meta.setdefault("slug", path.stem)
        posts.append(meta)
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    return posts


@router.get("/blog", response_class=HTMLResponse, include_in_schema=False)
async def blog_index(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "marketing/blog_index.html", {
        "posts": _list_posts(),
    })


@router.get("/blog/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def blog_post(slug: str, request: Request):
    post = _load_post(slug)
    if not post:
        raise HTTPException(404, "Post not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "marketing/blog_post.html", {
        "meta":  post["meta"],
        "html":  post["html"],
    })
