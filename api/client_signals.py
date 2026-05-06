"""
Client Signal Leads API — surfaces buyer-intent signals found by client_signal_listener.

Signal leads are people/posts found on social/web who are ALREADY looking for
what the client sells. They are NOT cold contacts. Every response includes the
"ReachNG found this" label so the client always knows these are uncontacted leads.

Endpoints:
  GET  /client-signals/{client_name}          — pending signals for this client
  POST /client-signals/{client_name}/{id}/draft — generate HITL outreach draft
  POST /client-signals/{client_name}/{id}/skip  — discard signal
  POST /client-signals/run/{client_name}       — trigger manual listener run
"""
from fastapi import APIRouter, HTTPException
from bson import ObjectId
import structlog

from tools.client_signal_listener import (
    get_pending_signals,
    skip_signal,
    mark_signal_drafted,
    get_signal_queue,
    run_client_signal_listener,
)

log = structlog.get_logger()
router = APIRouter(prefix="/client-signals", tags=["Client Signals"])


# ── GET pending signals ───────────────────────────────────────────────────────

@router.get("/{client_name}")
async def list_signals(client_name: str, limit: int = 20):
    signals = get_pending_signals(client_name, limit=limit)
    return {
        "client": client_name,
        "signals": signals,
        "label": "ReachNG found these — they haven't contacted you yet.",
    }


# ── Draft from signal ─────────────────────────────────────────────────────────

@router.post("/{client_name}/{signal_id}/draft")
async def draft_from_signal(client_name: str, signal_id: str):
    """
    Generate a HITL outreach draft for a signal lead.
    Haiku writes a short warm intro referencing their original post.
    """
    from api.clients import get_clients
    from tools.hitl import queue_draft
    import anthropic
    from config import get_settings

    # Fetch signal doc
    try:
        doc = get_signal_queue().find_one({"_id": ObjectId(signal_id)})
    except Exception:
        raise HTTPException(400, "Invalid signal ID")
    if not doc:
        raise HTTPException(404, "Signal not found")
    if doc.get("client_name") != client_name:
        raise HTTPException(403, "Signal does not belong to this client")

    # Fetch client brief
    client = get_clients().find_one(
        {"name": {"$regex": f"^{client_name}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{client_name}' not found")

    brief   = client.get("brief", "")
    channel = client.get("preferred_channel", "whatsapp")
    handle  = doc.get("handle", "")
    post    = doc.get("post_text", "")
    platform = doc.get("platform", "web")
    phone   = doc.get("phone")

    # Build draft via Haiku
    prompt = f"""You are a warm, human sales assistant for {client_name}.

Client brief:
{brief}

A potential customer posted this on {platform}:
"{post}"

Write a SHORT (2-3 sentences) warm {channel} outreach message to this person.
- Acknowledge what they're looking for (without quoting them verbatim)
- Briefly explain how {client_name} can help
- End with a soft CTA (invite them to reply, visit, or ask a question)
- Sound natural and friendly — not salesy
- No emojis unless the brief uses them
- Do NOT mention that you found this on social media — lead naturally

Return ONLY the message text."""

    try:
        client_ai = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        resp = client_ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        draft_text = resp.content[0].text.strip()
    except Exception as e:
        log.error("signal_draft_haiku_failed", signal_id=signal_id, error=str(e))
        raise HTTPException(500, "Draft generation failed")

    # Queue to HITL
    contact_id = f"signal_{signal_id}"
    display_name = doc.get("display_name") or handle or "Signal Lead"

    draft_id = queue_draft(
        contact_id=contact_id,
        contact_name=display_name,
        vertical=doc.get("vertical", "hospitality"),
        channel=channel,
        message=draft_text,
        phone=phone,
        source="client_signal",
        client_name=client_name,
        inbound_context=post,
    )

    # Mark signal as drafted
    mark_signal_drafted(signal_id, str(draft_id))

    log.info("signal_draft_queued", client=client_name, signal_id=signal_id)
    return {
        "success": True,
        "draft_queued": True,
        "draft_preview": draft_text[:200],
        "channel": channel,
        "contact": display_name,
    }


# ── Skip signal ───────────────────────────────────────────────────────────────

@router.post("/{client_name}/{signal_id}/skip")
async def skip_signal_endpoint(client_name: str, signal_id: str):
    ok = skip_signal(signal_id)
    if not ok:
        raise HTTPException(404, "Signal not found")
    return {"success": True}


# ── Manual trigger ────────────────────────────────────────────────────────────

@router.post("/run/{client_name}")
async def trigger_listener(client_name: str):
    """Manually trigger signal listener for one client (admin use)."""
    from api.clients import get_clients

    client = get_clients().find_one(
        {"name": {"$regex": f"^{client_name}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{client_name}' not found")

    result = await run_client_signal_listener(
        client_name=client_name,
        vertical=client.get("vertical", "hospitality"),
        extra_queries=client.get("signal_queries") or [],
    )
    return result
