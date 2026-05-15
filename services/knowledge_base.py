"""
Client Knowledge Base — per-client document store with scope-locked retrieval.

Why this exists
---------------
Clients drop their menus, FAQs, policies, pricing sheets, refund rules into a
folder. At draft time, the agent fetches the most relevant chunks and injects
them into the prompt. The customer asks "what's your refund policy?" → the agent
quotes the actual policy from the client's uploaded doc, not a guess.

v1 retrieval: lightweight token-overlap scoring. No external embedding API needed.
Good enough for the typical Lagos SME KB (menus, FAQs, policies — usually <100
chunks per client). The interface keeps `embedding: list[float] | None` open so
we can swap to Voyage / OpenAI embeddings later without breaking callers.

Scope rule (P0): every read/write requires a non-empty `client_id`. Calls with
no client_id raise `KBScopeViolationError`. One client's KB chunks can never
surface in another client's drafts.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db

log = structlog.get_logger()


# ─── Errors ───────────────────────────────────────────────────────────────────

class KBScopeViolationError(Exception):
    """P0 — refuses any KB op without a client_id."""


# ─── Collections ──────────────────────────────────────────────────────────────

def get_docs_col():
    return get_db()["client_kb_docs"]


def get_chunks_col():
    return get_db()["client_kb_chunks"]


def ensure_kb_indexes() -> None:
    docs = get_docs_col()
    docs.create_index([("client_id", ASCENDING), ("uploaded_at", DESCENDING)])
    docs.create_index([("client_id", ASCENDING), ("title", ASCENDING)])

    chunks = get_chunks_col()
    chunks.create_index([("client_id", ASCENDING), ("doc_id", ASCENDING)])
    chunks.create_index([("client_id", ASCENDING)])


# ─── Scope guard ──────────────────────────────────────────────────────────────

def _require_scope(client_id: Optional[str]) -> str:
    if not client_id or not str(client_id).strip():
        raise KBScopeViolationError(
            "knowledge_base access attempted without client_id — P0 violation"
        )
    return str(client_id).strip()


# ─── Text extraction ──────────────────────────────────────────────────────────

def extract_text(file_bytes: bytes, filename: str, mime_type: Optional[str] = None) -> str:
    """Extract plain text from PDF / TXT / MD / CSV / HTML uploads.

    Heavy formats (.docx, .pptx, .xlsx) are deferred to a future pass — clients
    can paste content via the manual entry endpoint as a workaround.
    """
    name_lower = (filename or "").lower()
    mime = (mime_type or "").lower()

    if name_lower.endswith(".pdf") or "pdf" in mime:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages = [(p.extract_text() or "") for p in pdf.pages]
                return "\n\n".join(p for p in pages if p.strip())
        except Exception as e:
            log.warning("pdfplumber_failed", error=str(e), filename=filename)
            return ""

    if name_lower.endswith((".txt", ".md", ".markdown", ".csv")) or mime.startswith("text/"):
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    if name_lower.endswith((".html", ".htm")) or "html" in mime:
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            # Strip tags primitively
            return re.sub(r"<[^>]+>", " ", text)
        except Exception:
            return ""

    # Last-ditch try-as-utf8
    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


# ─── Chunking ─────────────────────────────────────────────────────────────────

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def chunk_text(text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks. Prefers sentence boundaries when close."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        # Snap to nearest sentence boundary within the last 80 chars
        if end < n:
            snap = text.rfind(". ", max(i, end - 80), end)
            if snap != -1 and snap > i + chunk_size // 2:
                end = snap + 1
        chunks.append(text[i:end].strip())
        if end >= n:
            break
        i = max(i + 1, end - overlap)
    return [c for c in chunks if c]


# ─── Tokenisation for scoring ─────────────────────────────────────────────────

_WORD_RE = re.compile(r"[A-Za-z0-9₦]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "my", "your", "our",
    "do", "does", "did", "have", "has", "had", "will", "would", "should", "can",
    "could", "may", "might", "if", "as", "at", "by", "from", "up", "down", "out",
    "so", "than", "then", "too", "very", "just", "also", "any", "some", "what",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(text or "")
            if len(t) >= 2 and t.lower() not in _STOPWORDS}


# ─── Storage ──────────────────────────────────────────────────────────────────

@dataclass
class StoredDoc:
    doc_id: str
    title: str
    chunk_count: int


def add_document(
    client_id: str,
    *,
    title: str,
    raw_text: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> StoredDoc:
    """Add a document. Pass `raw_text` (manual paste) OR (file_bytes + filename).

    Scope-locked. Returns the stored doc summary.
    """
    cid = _require_scope(client_id)
    text = (raw_text or "").strip()
    if not text and file_bytes:
        text = extract_text(file_bytes, filename or "", mime_type)
    if not text:
        raise ValueError("knowledge_base: no extractable text")

    now = datetime.now(timezone.utc)
    doc = {
        "client_id":    cid,
        "title":        (title or filename or "Untitled").strip()[:200],
        "source":       "file" if file_bytes else "paste",
        "filename":     (filename or "")[:200] or None,
        "mime_type":    (mime_type or "")[:80] or None,
        "byte_size":    len(file_bytes) if file_bytes else len(text.encode("utf-8")),
        "text_length":  len(text),
        "tags":         list({(t or "").strip().lower() for t in (tags or []) if (t or "").strip()})[:8],
        "uploaded_at":  now,
    }
    res = get_docs_col().insert_one(doc)
    doc_id = str(res.inserted_id)

    chunks = chunk_text(text)
    if chunks:
        chunk_docs = [{
            "client_id":   cid,
            "doc_id":      doc_id,
            "doc_title":   doc["title"],
            "chunk_index": i,
            "text":        c,
            "tokens":      list(_tokens(c)),
            "embedding":   None,            # reserved for future
            "created_at":  now,
        } for i, c in enumerate(chunks)]
        get_chunks_col().insert_many(chunk_docs)

    log.info("kb_doc_added", client_id=cid, doc_id=doc_id,
             title=doc["title"], chunks=len(chunks))
    return StoredDoc(doc_id=doc_id, title=doc["title"], chunk_count=len(chunks))


def list_documents(client_id: str, limit: int = 100) -> list[dict]:
    cid = _require_scope(client_id)
    docs = list(get_docs_col().find({"client_id": cid}).sort("uploaded_at", -1).limit(limit))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def delete_document(client_id: str, doc_id: str) -> int:
    """Delete a doc and all its chunks. Returns 1 if doc removed, 0 otherwise."""
    cid = _require_scope(client_id)
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return 0
    # Scoped delete — wrong-client delete simply matches zero docs
    result = get_docs_col().delete_one({"_id": oid, "client_id": cid})
    if result.deleted_count:
        get_chunks_col().delete_many({"client_id": cid, "doc_id": doc_id})
        log.info("kb_doc_deleted", client_id=cid, doc_id=doc_id)
    return result.deleted_count


# ─── Retrieval ────────────────────────────────────────────────────────────────

@dataclass
class KBHit:
    text: str
    doc_title: str
    score: float


def search_kb(
    client_id: str,
    query: str,
    *,
    top_k: int = 4,
    min_score: float = 0.10,
) -> list[KBHit]:
    """Return top-K chunks ranked by token-overlap score. Scope-locked.

    Score = |query ∩ chunk| / |query|. Cheap, no extra deps, good enough for
    KBs under ~100 chunks. Swap implementation when we add embeddings.
    """
    cid = _require_scope(client_id)
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    # Pull only chunks that share at least one query token — DB-side filter
    # keeps this fast as the corpus grows. Fall back to a tag-scan otherwise.
    cursor = get_chunks_col().find(
        {"client_id": cid, "tokens": {"$in": list(q_tokens)}},
        {"text": 1, "tokens": 1, "doc_title": 1},
    ).limit(200)

    hits: list[KBHit] = []
    for c in cursor:
        c_tokens = set(c.get("tokens") or [])
        overlap = len(q_tokens & c_tokens)
        if overlap == 0:
            continue
        score = overlap / max(1, len(q_tokens))
        if score < min_score:
            continue
        hits.append(KBHit(
            text=c["text"], doc_title=c.get("doc_title", "(untitled)"), score=score,
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def fetch_kb_block(
    client_id: str,
    query: str,
    *,
    top_k: int = 4,
    char_budget: int = 1600,
) -> str:
    """Return a formatted text block for prompt injection, or empty string.

    Stays under `char_budget` to keep token costs predictable.
    """
    hits = search_kb(client_id, query, top_k=top_k)
    if not hits:
        return ""

    lines = ["Relevant content from this business's knowledge base — quote / paraphrase as needed:"]
    used = 0
    for h in hits:
        excerpt = h.text.strip()
        if used + len(excerpt) > char_budget:
            excerpt = excerpt[: max(0, char_budget - used)].rstrip() + "…"
        if not excerpt:
            break
        lines.append(f"\n[{h.doc_title}]\n{excerpt}")
        used += len(excerpt)
        if used >= char_budget:
            break
    return "\n".join(lines)
