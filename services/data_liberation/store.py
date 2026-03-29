"""
MongoDB store for Data Liberation chunks.
Each chunk = one meaningful piece of a client's walled data.
"""
from datetime import datetime, timezone
from database import get_db
from pymongo import ASCENDING, TEXT
import structlog

log = structlog.get_logger()


def get_data_chunks():
    return get_db()["data_chunks"]


def ensure_data_indexes():
    col = get_data_chunks()
    col.create_index([("client_name", ASCENDING)])
    col.create_index([("source_file", ASCENDING)])
    col.create_index([("content", TEXT)])   # full-text search fallback


def save_chunks(client_name: str, source_file: str, file_type: str, chunks: list[dict]) -> int:
    """
    Save extracted chunks for a client.
    Each chunk: {content: str, metadata: dict}
    Returns number of chunks saved.
    """
    col = get_data_chunks()
    now = datetime.now(timezone.utc)

    docs = [
        {
            "client_name": client_name.lower(),
            "source_file": source_file,
            "file_type": file_type,
            "content": chunk["content"],
            "metadata": chunk.get("metadata", {}),
            "created_at": now,
        }
        for chunk in chunks
        if chunk.get("content", "").strip()
    ]

    if docs:
        col.insert_many(docs)
        log.info("chunks_saved", client=client_name, file=source_file, count=len(docs))

    return len(docs)


def get_chunks_for_query(client_name: str, limit: int = 40) -> list[dict]:
    """
    Retrieve the most recent chunks for a client to pass to Claude as context.
    For most Lagos business data volumes, 40 chunks covers the full dataset.
    """
    col = get_data_chunks()
    return list(
        col.find(
            {"client_name": client_name.lower()},
            {"_id": 0, "content": 1, "source_file": 1, "metadata": 1},
        )
        .sort("created_at", -1)
        .limit(limit)
    )


def get_client_sources(client_name: str) -> list[dict]:
    """Return a list of all files ingested for a client."""
    col = get_data_chunks()
    pipeline = [
        {"$match": {"client_name": client_name.lower()}},
        {"$group": {
            "_id": "$source_file",
            "file_type": {"$first": "$file_type"},
            "chunk_count": {"$sum": 1},
            "ingested_at": {"$min": "$created_at"},
        }},
        {"$sort": {"ingested_at": -1}},
    ]
    return [
        {
            "source_file": r["_id"],
            "file_type": r["file_type"],
            "chunk_count": r["chunk_count"],
            "ingested_at": r["ingested_at"].isoformat(),
        }
        for r in col.aggregate(pipeline)
    ]


def delete_client_data(client_name: str, source_file: str | None = None) -> int:
    """Delete chunks for a client. Optionally scope to a single file."""
    col = get_data_chunks()
    query = {"client_name": client_name.lower()}
    if source_file:
        query["source_file"] = source_file
    result = col.delete_many(query)
    log.info("chunks_deleted", client=client_name, file=source_file, count=result.deleted_count)
    return result.deleted_count
