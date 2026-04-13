"""
Outreach memory — tracks every contact and every message sent.
Prevents duplicate outreach, enforces daily limits, surfaces follow-up candidates.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from database import get_contacts, get_outreach_log
from config import get_settings
from tools.scoring import score_contact


# ─── Nigerian state extraction ────────────────────────────────────────────────

# Known Nigerian states + FCT. Used to tag contacts from their address string.
_NG_STATES = [
    "Lagos", "Abuja", "FCT", "Rivers", "Ogun", "Oyo", "Kano", "Kaduna",
    "Delta", "Anambra", "Enugu", "Imo", "Akwa Ibom", "Cross River", "Edo",
    "Benue", "Plateau", "Kwara", "Niger", "Kogi", "Ekiti", "Ondo", "Osun",
    "Abia", "Ebonyi", "Bayelsa", "Taraba", "Adamawa", "Borno", "Yobe",
    "Gombe", "Bauchi", "Jigawa", "Kebbi", "Sokoto", "Zamfara", "Nasarawa",
]

def _extract_state(address: Optional[str]) -> Optional[str]:
    """Best-effort: pull Nigerian state name from a formatted address string."""
    if not address:
        return None
    addr_upper = address.upper()
    for state in _NG_STATES:
        if state.upper() in addr_upper:
            return "FCT" if state == "Abuja" else state
    # Fallback: second-to-last comma-separated segment often contains state
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        candidate = parts[-2].strip().split()[0]
        if len(candidate) > 3:
            return candidate
    return None


# ─── Contact status states ────────────────────────────────────────────────────
class Status:
    NOT_CONTACTED = "not_contacted"
    CONTACTED = "contacted"
    REPLIED = "replied"
    CONVERTED = "converted"
    OPTED_OUT = "opted_out"
    INVALID = "invalid"


# ─── Contact operations ───────────────────────────────────────────────────────

def upsert_contact(
    place_id: str,
    name: str,
    vertical: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    website: Optional[str] = None,
    rating: Optional[float] = None,
    category: Optional[str] = None,
    client_name: Optional[str] = None,
    source: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Insert or update a contact. Returns the contact _id as string."""
    contacts = get_contacts()
    now = datetime.now(timezone.utc)

    lead_score = score_contact(
        vertical=vertical,
        rating=rating,
        has_phone=bool(phone),
        has_website=bool(website),
        category=category,
    )

    state = _extract_state(address)

    doc = {
        "place_id": place_id,
        "name": name,
        "vertical": vertical,
        "lead_score": lead_score,
        "updated_at": now,
    }
    # Only include indexed fields when they have values — avoids unique-index
    # violations on null (even non-sparse indexes ignore absent fields).
    if phone:
        doc["phone"] = phone
    if email:
        doc["email"] = email
    if address:
        doc["address"] = address
    if website:
        doc["website"] = website
    if rating is not None:
        doc["rating"] = rating
    if category:
        doc["category"] = category
    if state:
        doc["state"] = state
    if client_name:
        doc["client_name"] = client_name
    if source:
        doc["source"] = source
    if platform:
        doc["platform"] = platform

    # Compound filter: scoped to client in agency mode, global otherwise.
    # This allows multiple clients to independently contact the same business
    # without the lead pool being exhausted across clients.
    filter_key: dict = {"place_id": place_id}
    if client_name:
        filter_key["client_name"] = client_name

    try:
        result = contacts.update_one(
            filter_key,
            {
                "$set": doc,
                "$setOnInsert": {
                    "status": Status.NOT_CONTACTED,
                    "outreach_count": 0,
                    "created_at": now,
                    "next_followup_at": None,
                },
            },
            upsert=True,
        )
    except Exception as exc:
        # Sparse index not yet applied on running instance — fall back to find
        if "DuplicateKeyError" in type(exc).__name__ or "E11000" in str(exc):
            contact = contacts.find_one(filter_key, {"_id": 1})
            if contact:
                return str(contact["_id"])
            # email collision from a different place_id — skip silently
            raise
        raise

    if result.upserted_id:
        return str(result.upserted_id)

    contact = contacts.find_one(filter_key, {"_id": 1})
    return str(contact["_id"])


def has_been_contacted(place_id: str, client_name: Optional[str] = None) -> bool:
    """True if we've already reached out to this contact.

    When client_name is provided (agency mode), dedup is scoped to that client —
    so multiple clients can independently contact the same business without collision.
    When no client_name is given, falls back to global dedup (general campaigns).

    Lead refresh: contacts last reached more than LEAD_REFRESH_DAYS ago (default 90)
    are treated as fresh again — except opted_out and converted which are permanent.
    """
    query = {"place_id": place_id}
    if client_name:
        query["client_name"] = client_name
    contact = get_contacts().find_one(query, {"status": 1, "last_contacted_at": 1})
    if not contact:
        return False
    status = contact.get("status")
    # Permanent exclusions — never re-contact
    if status in (Status.OPTED_OUT, Status.CONVERTED):
        return True
    if status == Status.NOT_CONTACTED:
        return False
    # Stale lead refresh — re-qualify if last contacted > LEAD_REFRESH_DAYS ago
    last_contacted = contact.get("last_contacted_at")
    if last_contacted:
        settings = get_settings()
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.lead_refresh_days)
        if last_contacted < cutoff:
            return False  # Eligible for fresh outreach
    return True


def get_daily_send_count() -> int:
    """How many messages we've sent today."""
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return get_outreach_log().count_documents({"sent_at": {"$gte": start_of_day}})


def is_daily_limit_reached() -> bool:
    settings = get_settings()
    return get_daily_send_count() >= settings.daily_send_limit


def record_outreach(
    contact_id: str,
    channel: str,          # "whatsapp" | "email"
    message: str,
    attempt_number: int = 1,
) -> str:
    """Log a sent message and update contact status. Returns log entry _id."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    next_followup = now + timedelta(hours=settings.followup_delay_hours)

    log = get_outreach_log()
    entry = log.insert_one({
        "contact_id": ObjectId(contact_id),
        "channel": channel,
        "message": message,
        "attempt_number": attempt_number,
        "sent_at": now,
    })

    get_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {
            "$set": {
                "status": Status.CONTACTED,
                "last_contacted_at": now,
                "next_followup_at": next_followup,
            },
            "$inc": {"outreach_count": 1},
        },
    )

    return str(entry.inserted_id)


def mark_replied(contact_id: str):
    get_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {"status": Status.REPLIED, "replied_at": datetime.now(timezone.utc)}}
    )


def mark_converted(contact_id: str):
    get_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {"status": Status.CONVERTED, "converted_at": datetime.now(timezone.utc)}}
    )


def mark_opted_out(contact_id: str):
    get_contacts().update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": {"status": Status.OPTED_OUT}}
    )


def get_followup_candidates(vertical: Optional[str] = None) -> list[dict]:
    """Return contacts due for follow-up that haven't exceeded max attempts."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    query = {
        "status": Status.CONTACTED,
        "next_followup_at": {"$lte": now},
        "outreach_count": {"$lt": settings.max_followup_attempts + 1},
    }
    if vertical:
        query["vertical"] = vertical

    return list(get_contacts().find(query).limit(20))


def get_pipeline_stats(vertical: Optional[str] = None, client_name: Optional[str] = None) -> dict:
    """Summary counts per status + source/platform breakdown for the dashboard."""
    match: dict = {}
    if vertical:
        match["vertical"] = vertical
    if client_name:
        match["client_name"] = client_name
    contacts = get_contacts()

    status_rows = list(contacts.aggregate([
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]))
    stats = {row["_id"]: row["count"] for row in status_rows}

    # Source breakdown: maps / apollo / social
    source_rows = list(contacts.aggregate([
        {"$match": match},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]))
    stats["by_source"] = {(row["_id"] or "unknown"): row["count"] for row in source_rows}

    # Platform breakdown for social leads: instagram / tiktok / twitter / facebook
    platform_rows = list(contacts.aggregate([
        {"$match": {**match, "source": "social"}},
        {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
    ]))
    stats["by_platform"] = {(row["_id"] or "unknown"): row["count"] for row in platform_rows}

    stats["daily_sent"] = get_daily_send_count()
    return stats
