"""
B2C CSV Import — parse a client's customer list and load into MongoDB.

Accepts CSV with these columns (flexible — auto-detects headers):
  Required (at least one):  phone | whatsapp | mobile | number
  Optional:                 name | first_name | last_name | email | notes | tags

Consent model:
  - Client uploading the CSV is asserting opt-in consent for their customers.
  - Every imported contact gets `consent_source: "client_csv"`.
  - Opted-out contacts (status=opted_out) are never re-imported.
  - Contacts already messaged within 14 days are skipped.
"""
import csv
import io
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional
from database import get_db
import structlog

log = structlog.get_logger()

# ─── Column aliases ───────────────────────────────────────────────────────────
_PHONE_COLS   = {"phone", "whatsapp", "mobile", "number", "tel", "telephone", "contact"}
_NAME_COLS    = {"name", "full_name", "fullname", "customer", "client"}
_FNAME_COLS   = {"first_name", "firstname", "first"}
_LNAME_COLS   = {"last_name", "lastname", "surname", "last"}
_EMAIL_COLS   = {"email", "email_address", "mail"}
_NOTES_COLS   = {"notes", "note", "comment", "comments", "description"}
_TAGS_COLS    = {"tags", "tag", "segment", "group", "category"}


# ─── Public interface ─────────────────────────────────────────────────────────

def parse_and_import_csv(
    csv_bytes: bytes,
    client_name: str,
    vertical: str,
    campaign_tag: Optional[str] = None,
    column_overrides: Optional[dict] = None,
) -> dict:
    """
    Parse a CSV file and upsert contacts into MongoDB b2c_contacts collection.

    `column_overrides` lets the caller pin specific columns to specific fields
    when auto-detect fails (e.g. headers like "GSM", "Cell", "Mobile Number").
    Shape: {"phone": "GSM", "name": "Customer Name", "email": "Mail"}.
    Overrides win over auto-detect; auto-detect fills any field not overridden.

    Returns:
        {
            "imported": int,
            "skipped_duplicate": int,
            "skipped_opted_out": int,
            "skipped_no_contact": int,
            "errors": int,
            "total_rows": int,
        }
    """
    text = csv_bytes.decode("utf-8-sig", errors="ignore")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("CSV has no headers")

    col_map = _merge_column_map(_map_columns(reader.fieldnames), column_overrides, list(reader.fieldnames))
    if not col_map.get("phone"):
        raise ValueError("CSV must have a phone/whatsapp column. Found: " + str(list(reader.fieldnames)))

    stats = {"imported": 0, "skipped_duplicate": 0, "skipped_opted_out": 0, "skipped_no_contact": 0, "errors": 0, "total_rows": 0}
    col = _get_b2c_contacts()

    for row in reader:
        stats["total_rows"] += 1
        try:
            phone = _clean_phone(row.get(col_map.get("phone", ""), ""))
            if not phone:
                stats["skipped_no_contact"] += 1
                continue

            email = _clean_email(row.get(col_map.get("email", ""), "")) if col_map.get("email") else None
            name  = _extract_name(row, col_map)
            notes_raw = row.get(col_map.get("notes", ""), "").strip() if col_map.get("notes") else None
            notes = _sanitize_text_field(notes_raw) if notes_raw else None
            tags  = [_sanitize_text_field(t) for t in (_parse_tags(row.get(col_map.get("tags", ""), "")) if col_map.get("tags") else [])]
            if campaign_tag:
                tags.append(campaign_tag)

            contact_id = _upsert_b2c_contact(
                col=col,
                phone=phone,
                email=email,
                name=name,
                client_name=client_name,
                vertical=vertical,
                notes=notes,
                tags=tags,
                stats=stats,
            )
            if contact_id:
                stats["imported"] += 1

        except Exception as exc:
            log.warning("csv_row_error", row=row, error=str(exc))
            stats["errors"] += 1

    log.info("csv_import_done", client=client_name, **stats)
    return stats


def preview_csv(
    csv_bytes: bytes,
    client_name: Optional[str] = None,
    column_overrides: Optional[dict] = None,
) -> dict:
    """Parse a CSV without writing to Mongo. Returns the same stats shape as
    parse_and_import_csv plus a small sample of how rows would be normalised.

    Used by the portal upload flow to surface a "342 valid, 18 duplicates,
    7 invalid — proceed?" confirmation step before committing the import.
    """
    text = csv_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return {
            "ok": False,
            "error": "CSV has no headers",
            "total_rows": 0,
            "valid": 0,
            "duplicates_in_file": 0,
            "duplicates_existing": 0,
            "opted_out_existing": 0,
            "invalid_phone": 0,
            "sample": [],
            "headers": [],
            "column_map": {},
        }

    col_map = _merge_column_map(_map_columns(reader.fieldnames), column_overrides, list(reader.fieldnames))
    if not col_map.get("phone"):
        return {
            "ok": False,
            "error": "CSV must have a phone/whatsapp/mobile/number column. Use the column-mapper below to pick one manually.",
            "total_rows": 0,
            "valid": 0,
            "duplicates_in_file": 0,
            "duplicates_existing": 0,
            "opted_out_existing": 0,
            "invalid_phone": 0,
            "sample": [],
            "headers": list(reader.fieldnames),
            "column_map": col_map,
        }

    contacts_col = _get_b2c_contacts()
    seen_phones_in_file: set[str] = set()
    valid = 0
    dup_in_file = 0
    dup_existing = 0
    opted_out = 0
    invalid_phone = 0
    total = 0
    sample: list[dict] = []

    for row in reader:
        total += 1
        phone_raw = row.get(col_map.get("phone", ""), "")
        phone = _clean_phone(phone_raw)
        if not phone:
            invalid_phone += 1
            continue
        if phone in seen_phones_in_file:
            dup_in_file += 1
            continue
        seen_phones_in_file.add(phone)

        existing = contacts_col.find_one({"phone": phone}, {"status": 1})
        if existing:
            if existing.get("status") == "opted_out":
                opted_out += 1
            else:
                dup_existing += 1
            continue

        valid += 1
        if len(sample) < 5:
            sample.append({
                "name": _extract_name(row, col_map),
                "phone": phone,
                "email": _clean_email(row.get(col_map.get("email", ""), "")) if col_map.get("email") else None,
            })

    return {
        "ok": True,
        "total_rows": total,
        "valid": valid,
        "duplicates_in_file": dup_in_file,
        "duplicates_existing": dup_existing,
        "opted_out_existing": opted_out,
        "invalid_phone": invalid_phone,
        "sample": sample,
        "headers": list(reader.fieldnames),
        "column_map": col_map,
    }


def get_b2c_contacts_for_campaign(client_name: str, vertical: str, limit: int = 200) -> list[dict]:
    """
    Return B2C contacts for this client+vertical that haven't been contacted yet
    and haven't opted out. Used by the B2C campaign runner.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    col = _get_b2c_contacts()
    contacts = list(
        col.find({
            "client_name": client_name,
            "vertical": vertical,
            "status": {"$nin": ["opted_out", "converted"]},
            "$or": [
                {"last_contacted_at": {"$lt": cutoff}},
                {"last_contacted_at": {"$exists": False}},
            ],
        })
        .sort("created_at", 1)
        .limit(limit)
    )
    return contacts


def mark_b2c_contacted(contact_id: str):
    from bson import ObjectId
    _get_b2c_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {"status": "contacted", "last_contacted_at": datetime.now(timezone.utc),
                  "outreach_count": 1}},
    )


def mark_b2c_opted_out(contact_id: str):
    from bson import ObjectId
    _get_b2c_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {"status": "opted_out", "opted_out_at": datetime.now(timezone.utc)}},
    )


def ensure_b2c_indexes():
    col = _get_b2c_contacts()
    from pymongo import ASCENDING
    col.create_index([("phone", ASCENDING)], unique=True, sparse=True)
    col.create_index([("client_name", ASCENDING), ("vertical", ASCENDING)])
    col.create_index([("status", ASCENDING)])
    # Sequence engine — finds contacts whose next step is due.
    col.create_index([("next_due_at", ASCENDING), ("status", ASCENDING)], sparse=True)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_b2c_contacts():
    return get_db()["b2c_contacts"]


_OVERRIDABLE_FIELDS = {"phone", "email", "name", "first_name", "last_name", "notes", "tags"}


def _merge_column_map(
    auto_map: dict,
    overrides: Optional[dict],
    fieldnames: list[str],
) -> dict:
    """Merge user-supplied column overrides on top of auto-detected mapping.

    Overrides win where set. Empty / None override values are ignored.
    Override values must match an actual CSV header (case-sensitive) — anything
    that doesn't match is dropped silently rather than risk a key error.
    """
    if not overrides:
        return auto_map
    fieldset = set(fieldnames)
    out = dict(auto_map)
    for field, header in (overrides or {}).items():
        if field not in _OVERRIDABLE_FIELDS:
            continue
        header = (header or "").strip()
        if not header:
            continue
        if header not in fieldset:
            continue
        out[field] = header
    return out


def _map_columns(fieldnames: list) -> dict:
    """Map CSV column names to canonical field names."""
    mapping = {}
    for col in fieldnames:
        key = col.strip().lower().replace(" ", "_").replace("-", "_")
        if key in _PHONE_COLS and "phone" not in mapping:
            mapping["phone"] = col
        elif key in _EMAIL_COLS and "email" not in mapping:
            mapping["email"] = col
        elif key in _NAME_COLS and "name" not in mapping:
            mapping["name"] = col
        elif key in _FNAME_COLS and "first_name" not in mapping:
            mapping["first_name"] = col
        elif key in _LNAME_COLS and "last_name" not in mapping:
            mapping["last_name"] = col
        elif key in _NOTES_COLS and "notes" not in mapping:
            mapping["notes"] = col
        elif key in _TAGS_COLS and "tags" not in mapping:
            mapping["tags"] = col
    return mapping


def _clean_phone(raw: str) -> Optional[str]:
    """Normalize phone number to E.164-ish format."""
    digits = re.sub(r"[^\d+]", "", raw.strip())
    if not digits:
        return None
    # Nigerian numbers: if starts with 0, replace with +234
    if digits.startswith("0") and len(digits) == 11:
        digits = "+234" + digits[1:]
    # If no country code and 10 digits, assume Nigeria
    elif digits.isdigit() and len(digits) == 10:
        digits = "+234" + digits
    # Already has + prefix
    elif not digits.startswith("+"):
        digits = "+" + digits
    # Validate length (international: 8-15 digits after +)
    digit_only = digits.lstrip("+")
    if not (7 <= len(digit_only) <= 15):
        return None
    return digits


def _clean_email(raw: str) -> Optional[str]:
    val = raw.strip().lower()
    if "@" in val and "." in val.split("@")[-1]:
        return val
    return None


def _extract_name(row: dict, col_map: dict) -> str:
    if col_map.get("name"):
        name = _sanitize_text_field(row.get(col_map["name"], "").strip())
        if name:
            return name
    first = _sanitize_text_field(row.get(col_map.get("first_name", ""), "").strip())
    last  = _sanitize_text_field(row.get(col_map.get("last_name", ""), "").strip())
    if first or last:
        return f"{first} {last}".strip()
    return "Customer"


def _parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in re.split(r"[,;|]", raw) if t.strip()]


def _sanitize_text_field(val: str) -> str:
    """
    Prevent CSV formula injection.
    Cells starting with =, +, -, @, tab, or CR are treated as formulas
    by Excel/Google Sheets. Prefix with a single quote to neutralize.
    """
    if val and val[0] in ('=', '+', '-', '@', '\t', '\r', '|', '%'):
        return "'" + val
    return val


def _upsert_b2c_contact(
    col, phone: str, email: Optional[str], name: str,
    client_name: str, vertical: str, notes: Optional[str],
    tags: list, stats: dict,
) -> Optional[str]:
    """Insert or update B2C contact. Returns _id string or None if skipped."""
    now = datetime.now(timezone.utc)

    existing = col.find_one({"phone": phone}, {"_id": 1, "status": 1})
    if existing:
        if existing.get("status") == "opted_out":
            stats["skipped_opted_out"] += 1
            return None
        stats["skipped_duplicate"] += 1
        # Still update name/tags if we have better data
        col.update_one(
            {"_id": existing["_id"]},
            {"$set": {"updated_at": now}, "$addToSet": {"tags": {"$each": tags}}},
        )
        return None

    result = col.insert_one({
        "phone": phone,
        "email": email,
        "name": name,
        "client_name": client_name,
        "vertical": vertical,
        "notes": notes,
        "tags": tags,
        "status": "new",
        "consent_source": "client_csv",
        "outreach_count": 0,
        "last_contacted_at": None,
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)
