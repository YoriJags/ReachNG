"""
Natural language query engine for Data Liberation.
Passes the client's stored data chunks to Claude as context.
Claude reasons over the data and returns a structured answer.
"""
import anthropic
import structlog
from config import get_settings
from .store import get_chunks_for_query, get_client_sources

log = structlog.get_logger()

_SYSTEM = """You are a data analyst for a Lagos business. You have been given chunks of the client's own business data — spreadsheets, documents, records, and logs.

Your job:
- Answer the user's question using ONLY the data provided
- Be specific — cite numbers, dates, names from the data
- If the data doesn't contain enough information to answer, say so clearly
- Format your answer clearly: use bullet points or a short table if the data supports it
- Keep the answer concise and actionable
- Speak like a sharp Lagos business analyst — direct, no fluff"""


async def query_client_data(client_name: str, question: str) -> dict:
    """
    Answer a natural language question about a client's ingested data.
    Returns {answer, sources_used, chunks_searched}
    """
    chunks = get_chunks_for_query(client_name, limit=40)

    if not chunks:
        return {
            "answer": f"No data found for '{client_name}'. Upload files first via POST /api/v1/data/upload.",
            "sources_used": [],
            "chunks_searched": 0,
        }

    # Build context from chunks
    context_parts = []
    sources_used = set()
    for chunk in chunks:
        sources_used.add(chunk["source_file"])
        meta = chunk.get("metadata", {})
        label = f"[{chunk['source_file']}"
        if meta.get("sheet"):
            label += f" — Sheet: {meta['sheet']}"
        if meta.get("page"):
            label += f" — Page {meta['page']}"
        if meta.get("rows"):
            label += f" — Rows {meta['rows']}"
        label += "]"
        context_parts.append(f"{label}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    user_prompt = f"""CLIENT: {client_name}

DATA:
{context}

QUESTION: {question}

Answer based only on the data above."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    answer = response.content[0].text.strip()
    log.info("data_query_answered", client=client_name, question=question[:80])

    return {
        "answer": answer,
        "sources_used": sorted(sources_used),
        "chunks_searched": len(chunks),
    }


async def get_data_summary(client_name: str) -> dict:
    """
    Generate a plain-English summary of what data a client has uploaded.
    Useful for onboarding — shows them what the agent knows about their business.
    """
    sources = get_client_sources(client_name)
    if not sources:
        return {"summary": "No data uploaded yet.", "sources": []}

    source_list = "\n".join(
        f"- {s['source_file']} ({s['file_type']}, {s['chunk_count']} sections)"
        for s in sources
    )

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Summarise in 2 sentences what business data has been uploaded for client '{client_name}'. "
                f"Files:\n{source_list}\nBe specific and business-focused."
            ),
        }],
    )

    return {
        "summary": response.content[0].text.strip(),
        "sources": sources,
    }
