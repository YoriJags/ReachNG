from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from functools import lru_cache
from config import get_settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_uri)
    return _client


def get_db() -> Database:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def get_contacts() -> Collection:
    return get_db()["contacts"]


def get_outreach_log() -> Collection:
    return get_db()["outreach_log"]


def get_campaigns() -> Collection:
    return get_db()["campaigns"]


def get_replies() -> Collection:
    return get_db()["replies"]


def ensure_indexes():
    """Create all required indexes on startup."""
    contacts = get_contacts()

    # One-time migration: drop old single-field place_id index (replaced by compound below)
    # and ensure phone/email indexes are sparse. Safe to run repeatedly — drop is a no-op
    # if the index doesn't exist. We only drop specific named indexes, never blindly.
    for idx_name in ("place_id_1", "email_1", "phone_1"):
        try:
            contacts.drop_index(idx_name)
        except Exception:
            pass  # Index didn't exist — fine

    # create_index is idempotent: no-op if index already exists with same definition.
    # No drop before recreate — avoids the unsafe window between drop and creation
    # where uniqueness is unenforced under concurrent traffic.
    contacts.create_index([("phone", ASCENDING)], unique=True, sparse=True)
    contacts.create_index([("email", ASCENDING)], unique=True, sparse=True)
    # Compound unique: (place_id, client_name) — allows multiple clients to
    # independently contact the same business without lead pool exhaustion.
    # sparse=True handles non-agency records where client_name is absent.
    contacts.create_index(
        [("place_id", ASCENDING), ("client_name", ASCENDING)],
        unique=True,
        sparse=True,
        name="place_id_client_name_unique",
    )
    contacts.create_index([("vertical", ASCENDING)])
    contacts.create_index([("status", ASCENDING)])
    contacts.create_index([("next_followup_at", ASCENDING)])
    contacts.create_index([("lead_temperature", ASCENDING)])
    contacts.create_index([("client_name", ASCENDING)])

    log = get_outreach_log()
    log.create_index([("contact_id", ASCENDING)])
    log.create_index([("sent_at", DESCENDING)])
    log.create_index([("channel", ASCENDING)])

    replies = get_replies()
    replies.create_index([("unipile_message_id", ASCENDING)], unique=True)
    replies.create_index([("contact_id", ASCENDING)])
    replies.create_index([("received_at", DESCENDING)])
    replies.create_index([("channel", ASCENDING)])
