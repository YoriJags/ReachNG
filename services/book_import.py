"""
Client Book Onboarding v1 (SPRINT 2 #9 — slimmest slice).

Lets an owner bring their existing customer book into ReachNG so EYO knows
who's who from day 1. Two ingest paths today:

  - .vcf (vCard) file upload — works from any phone's Contacts export
  - Paste-in textarea — for owners with a Notes list, half-finished sheet, etc.

Both write to a new `client_book` collection (separate from cold-outreach `leads`
so we don't pollute that pipeline). Bucket triage + tone routing + WhatsApp
share-contact ingest are the full Phase 1.6 scope — not in v1.

Storage on `client_book`:
  { client_id, contact_name, contact_phone, contact_email, notes,
    source: "vcf" | "paste", import_id, created_at }
Storage on `book_imports`:
  { _id, client_id, source, filename?, raw_chars, parsed_count,
    deduped_count, created_at, uploader_ip }
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import structlog
from bson import ObjectId

from database import get_db

log = structlog.get_logger()


def _book():
    return get_db()["client_book"]


def _imports():
    return get_db()["book_imports"]


# ─── Normalisation ──────────────────────────────────────────────────────────

_PHONE_KEEP = re.compile(r"[^\d+]")


def _norm_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = _PHONE_KEEP.sub("", raw.strip())
    if not s:
        return None
    # Nigerian: 0xxx → +234xxx, 234xxx → +234xxx
    if s.startswith("0") and len(s) >= 10:
        s = "+234" + s[1:]
    elif s.startswith("234") and len(s) >= 12:
        s = "+" + s
    elif not s.startswith("+") and len(s) >= 10:
        s = "+234" + s[-10:]
    return s


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _extract_email(s: str) -> Optional[str]:
    m = _EMAIL_RE.search(s or "")
    return m.group(0).lower() if m else None


# ─── vCard parser (handles common Apple/Android exports — not full RFC) ─────

_VCARD_BLOCK = re.compile(r"BEGIN:VCARD(.*?)END:VCARD", re.DOTALL | re.IGNORECASE)


def parse_vcf(text: str) -> list[dict]:
    """Returns list of {contact_name, contact_phone, contact_email, notes} dicts.
    Lenient — silently skips malformed cards."""
    out: list[dict] = []
    for m in _VCARD_BLOCK.finditer(text or ""):
        block = m.group(1)
        contact = _parse_vcard_block(block)
        if contact and (contact.get("contact_phone") or contact.get("contact_email")):
            out.append(contact)
    return out


def _parse_vcard_block(block: str) -> dict:
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    note: Optional[str] = None

    # FN (full name) — preferred. Fallback to N (structured) if missing.
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Param-stripped key
        key = line.split(":", 1)[0].split(";", 1)[0].upper()
        val = line.split(":", 1)[1].strip() if ":" in line else ""

        if key == "FN" and not name:
            name = val
        elif key == "N" and not name:
            # N is Last;First;Middle;Prefix;Suffix
            parts = val.split(";")
            name = (parts[1] + " " + parts[0]).strip() if len(parts) >= 2 else val
        elif key == "TEL" and not phone:
            phone = _norm_phone(val)
        elif key == "EMAIL" and not email:
            email = val.lower() or None
        elif key == "NOTE" and not note:
            note = val[:500]

    return {
        "contact_name":  (name or "").strip() or None,
        "contact_phone": phone,
        "contact_email": email,
        "notes":         note,
    }


# ─── Paste-in parser ────────────────────────────────────────────────────────

def parse_paste(text: str) -> list[dict]:
    """One contact per line. Liberal — pulls phone + email + remaining-as-name."""
    out: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or len(line) < 4:
            continue
        # Phone heuristics: a long-ish digit sequence (with optional +)
        phone_match = re.search(r"\+?\d[\d\s\-()]{8,}", line)
        phone = _norm_phone(phone_match.group(0)) if phone_match else None
        email = _extract_email(line)
        # Strip phone + email from the line to leave the name
        residue = line
        if phone_match:
            residue = residue.replace(phone_match.group(0), "")
        if email:
            residue = residue.replace(email, "")
        residue = re.sub(r"[,·\-\|]+", " ", residue).strip()
        name = residue or None
        if not (phone or email):
            continue
        out.append({
            "contact_name":  name,
            "contact_phone": phone,
            "contact_email": email,
            "notes":         None,
        })
    return out


# ─── Persistence ────────────────────────────────────────────────────────────

def import_book(
    *,
    client_id: str,
    contacts: list[dict],
    source: str,
    filename: Optional[str] = None,
    raw_chars: int = 0,
    uploader_ip: Optional[str] = None,
) -> dict:
    """Write contacts + audit row. Dedupes by (client_id, contact_phone) and
    (client_id, contact_email). Returns counts."""
    if not client_id:
        raise ValueError("client_id required")
    now = datetime.now(timezone.utc)

    import_doc = {
        "client_id":     str(client_id),
        "source":        source,
        "filename":      filename,
        "raw_chars":     int(raw_chars or 0),
        "parsed_count":  len(contacts),
        "deduped_count": 0,
        "created_at":    now,
        "uploader_ip":   uploader_ip,
    }
    import_id = _imports().insert_one(import_doc).inserted_id

    added = 0
    deduped = 0
    book = _book()
    for c in contacts:
        phone = c.get("contact_phone")
        email = c.get("contact_email")
        if not (phone or email):
            continue
        # Dedupe per client + phone OR email
        q: dict = {"client_id": str(client_id), "$or": []}
        if phone: q["$or"].append({"contact_phone": phone})
        if email: q["$or"].append({"contact_email": email})
        if not q["$or"]:
            continue
        existing = book.find_one(q)
        if existing:
            deduped += 1
            continue
        book.insert_one({
            "client_id":     str(client_id),
            "contact_name":  c.get("contact_name"),
            "contact_phone": phone,
            "contact_email": email,
            "notes":         c.get("notes"),
            "source":        source,
            "import_id":     import_id,
            "created_at":    now,
        })
        added += 1

    _imports().update_one({"_id": import_id}, {"$set": {"deduped_count": deduped}})

    log.info("book_import_complete",
             client_id=str(client_id), source=source,
             parsed=len(contacts), added=added, deduped=deduped)
    return {
        "import_id":    str(import_id),
        "parsed":       len(contacts),
        "added":        added,
        "deduped":      deduped,
        "source":       source,
    }


# ─── Read ───────────────────────────────────────────────────────────────────

def list_imports(client_id: str, limit: int = 20) -> list[dict]:
    cur = _imports().find({"client_id": str(client_id)}).sort("created_at", -1).limit(limit)
    return list(cur)


def book_summary(client_id: str) -> dict:
    total = _book().count_documents({"client_id": str(client_id)})
    return {"total": total}


def ensure_book_indexes() -> None:
    book = _book()
    book.create_index([("client_id", 1), ("contact_phone", 1)], name="book_client_phone", sparse=True)
    book.create_index([("client_id", 1), ("contact_email", 1)], name="book_client_email", sparse=True)
    book.create_index([("client_id", 1), ("created_at", -1)],   name="book_client_recent")
    _imports().create_index([("client_id", 1), ("created_at", -1)], name="book_imports_recent")
