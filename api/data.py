"""
Data Liberation API — upload files, query them in plain English.
This is the "Walled Data" service: clients upload their PDFs, Excels, CSVs,
and WhatsApp exports, then ask questions in plain English via Claude.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from services.data_liberation import (
    ingest_file, query_client_data, get_client_sources, delete_client_data
)
from services.data_liberation.query import get_data_summary

router = APIRouter(prefix="/data", tags=["Data Liberation"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


# ─── Schemas ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    client_name: str
    question: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    client_name: str,
    file: UploadFile = File(...),
):
    """
    Upload a file for a client. Supported: PDF, Excel (.xlsx), CSV, TXT.
    The file is extracted, chunked, and stored in MongoDB.
    Once uploaded, the client can query the data in plain English.
    """
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max size is 20MB.")

    if not file.filename:
        raise HTTPException(400, "Filename required.")

    result = await ingest_file(
        client_name=client_name,
        filename=file.filename,
        content=content,
    )

    if result["status"] == "error":
        raise HTTPException(500, f"Ingestion failed: {result.get('error')}")

    return {
        "message": f"'{file.filename}' ingested successfully for {client_name}.",
        **result,
    }


@router.post("/query")
async def query_data(payload: QueryRequest):
    """
    Ask a plain-English question about a client's uploaded data.
    Claude reasons over the stored chunks and returns a structured answer.

    Examples:
    - "Which routes had the most delays last quarter?"
    - "What's the average days-to-close for Lekki properties?"
    - "Show me all outstanding invoices over ₦500k"
    - "Which driver had the most breakdowns this year?"
    """
    if not payload.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    result = await query_client_data(
        client_name=payload.client_name,
        question=payload.question,
    )
    return result


@router.get("/{client_name}/sources")
async def list_sources(client_name: str):
    """List all files uploaded for a client."""
    sources = get_client_sources(client_name)
    return {"client_name": client_name, "sources": sources, "total_files": len(sources)}


@router.get("/{client_name}/summary")
async def data_summary(client_name: str):
    """
    Get a plain-English summary of what data the agent knows about this client.
    Show this to new clients after their first upload.
    """
    return await get_data_summary(client_name)


@router.delete("/{client_name}")
async def delete_data(client_name: str, source_file: str | None = None):
    """
    Delete a client's data. Scope to a single file with ?source_file=filename.csv
    or delete everything for the client.
    """
    count = delete_client_data(client_name, source_file)
    scope = f"'{source_file}'" if source_file else "all files"
    return {
        "message": f"Deleted {count} chunks for {client_name} ({scope}).",
        "chunks_deleted": count,
    }
