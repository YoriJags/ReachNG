"""
Owner-voice control (SPRINT 2 #11) — v1.

The owner sends a WhatsApp voice note (or text) to EYO's number from THEIR
own phone. We detect it's the owner (sender_phone matches client.owner_phone),
parse intent with Haiku, apply the action, and reply with a one-line
confirmation from EYO via the client's own WhatsApp account.

V1 firm command classes (executed in-line):
  • status_check   — weekly stats: drafts queued/approved, lifetime deposits,
                     streak days, unread waiting, current pause state
  • pause          — set client.eyo_paused_until = now + N hours (default 12h).
                     The drafter checks this flag and short-circuits.
  • resume         — clear client.eyo_paused_until

Recognised but stubbed in v1 (replies "noted — Yori will action this manually"):
  • set_rule, update_pricing, bulk_approve

All other transcripts → ignored, normal drafter flow runs.

P0: Scope is enforced via the client doc match — we never act on a foreign
client_id. Confirmation reply goes back via the client's own Unipile account
(send_whatsapp_for_client), never the ReachNG default.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

from config import get_settings
from database import get_db

log = structlog.get_logger()

_PHONE_KEEP = re.compile(r"[^\d+]")


def _norm_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = _PHONE_KEEP.sub("", raw.strip())
    if not s:
        return None
    if s.startswith("0") and len(s) >= 10:
        s = "+234" + s[1:]
    elif s.startswith("234") and len(s) >= 12:
        s = "+" + s
    elif not s.startswith("+") and len(s) >= 10:
        s = "+234" + s[-10:]
    return s


def match_owner(sender_phone: str, client_doc: dict) -> bool:
    """True iff sender_phone is the owner's number on this client."""
    owner = _norm_phone(client_doc.get("owner_phone"))
    sender = _norm_phone(sender_phone)
    return bool(owner and sender and owner == sender)


# ─── Intent parsing ──────────────────────────────────────────────────────────

_ALLOWED_ACTIONS = {
    "status_check", "pause", "resume", "rescue_followup",
    "set_rule", "update_pricing", "bulk_approve",
    "none",
}

_INTENT_SYSTEM = (
    "You parse a Lagos business owner's WhatsApp voice/text command to their "
    "AI operator (EYO). Output STRICT JSON only — no prose, no markdown.\n\n"
    "Schema: {\"action\": one of [status_check, pause, resume, rescue_followup, "
    "set_rule, update_pricing, bulk_approve, none], \"params\": {object}, "
    "\"confidence\": 0.0-1.0}\n\n"
    "Examples:\n"
    "  'How am I doing this week?' → {\"action\":\"status_check\",\"params\":{},\"confidence\":0.95}\n"
    "  'Follow up everyone who asked price last week but didn't pay' → {\"action\":\"rescue_followup\",\"params\":{},\"confidence\":0.92}\n"
    "  'Chase the dead leads / find cash this week / wake up old enquiries' → {\"action\":\"rescue_followup\",\"params\":{},\"confidence\":0.85}\n"
    "  'Hold all replies until tomorrow morning' → {\"action\":\"pause\",\"params\":{\"hours\":12},\"confidence\":0.9}\n"
    "  'Pause EYO for 2 hours' → {\"action\":\"pause\",\"params\":{\"hours\":2},\"confidence\":0.95}\n"
    "  'Resume / unpause / go back on' → {\"action\":\"resume\",\"params\":{},\"confidence\":0.95}\n"
    "  'Update Friday minimum to 200k' → {\"action\":\"update_pricing\",\"params\":{\"note\":\"...\"},\"confidence\":0.7}\n"
    "  'Approve everything in the queue' → {\"action\":\"bulk_approve\",\"params\":{},\"confidence\":0.8}\n"
    "  'If anyone mentions wedding switch to bridal package' → {\"action\":\"set_rule\",\"params\":{\"text\":\"...\"},\"confidence\":0.7}\n"
    "  Customer messages (not commands) → {\"action\":\"none\",\"params\":{},\"confidence\":0.9}\n"
)


async def parse_intent(transcript: str) -> dict:
    """Returns {action, params, confidence}. action='none' if not a command."""
    settings = get_settings()
    if not settings.anthropic_api_key or not (transcript or "").strip():
        return {"action": "none", "params": {}, "confidence": 0.0}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            temperature=0.0,
            system=_INTENT_SYSTEM,
            messages=[{"role": "user", "content": transcript.strip()[:1000]}],
        )
        text = ""
        for block in resp.content or []:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        text = text.strip()
        # Tolerate ``` fences
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        data = json.loads(text)
        action = str(data.get("action", "none")).strip().lower()
        if action not in _ALLOWED_ACTIONS:
            action = "none"
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        conf = float(data.get("confidence", 0.0) or 0.0)
        return {"action": action, "params": params, "confidence": conf}
    except Exception as e:
        log.warning("owner_voice_intent_parse_failed", error=str(e))
        return {"action": "none", "params": {}, "confidence": 0.0}


# ─── Execution ───────────────────────────────────────────────────────────────

def _clients_col():
    return get_db()["clients"]


def _approvals_col():
    return get_db()["approvals"]


def _do_pause(client: dict, hours: float) -> str:
    h = max(0.25, min(72.0, float(hours or 12)))
    until = datetime.now(timezone.utc) + timedelta(hours=h)
    _clients_col().update_one(
        {"_id": client["_id"]},
        {"$set": {"eyo_paused_until": until,
                  "eyo_paused_at":    datetime.now(timezone.utc)}},
    )
    # Lagos-local hour for confirmation
    local = until.astimezone(timezone(timedelta(hours=1)))
    return (f"Holding all replies until {local.strftime('%a %-I:%M%p').lower()}. "
            f"Say *resume* anytime to lift it.")


def _do_resume(client: dict) -> str:
    _clients_col().update_one(
        {"_id": client["_id"]},
        {"$unset": {"eyo_paused_until": "", "eyo_paused_at": ""}},
    )
    return "Back on. EYO will reply to incoming messages as normal."


def _do_status(client: dict) -> str:
    cid = str(client["_id"])
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    approvals = _approvals_col()
    queued = approvals.count_documents(
        {"client_id": cid, "status": {"$in": ["pending", "queued"]}})
    week_approved = approvals.count_documents(
        {"client_id": cid, "status": {"$in": ["approved", "auto_sent", "edited"]},
         "updated_at": {"$gte": week_ago}})
    # Streak (best effort)
    streak = 0
    try:
        from services.brief_streak import compute_streak
        streak = compute_streak(client.get("name", ""))
    except Exception:
        pass
    # Lifetime deposits (best effort)
    deposits_ngn = 0
    try:
        from services.brief_streak import cumulative_deposits_ngn
        deposits_ngn = cumulative_deposits_ngn(client.get("name", ""))
    except Exception:
        pass
    paused = client.get("eyo_paused_until")
    pause_line = ""
    if paused and paused > now:
        local = paused.astimezone(timezone(timedelta(hours=1)))
        pause_line = f"\n⏸ Paused until {local.strftime('%a %-I:%M%p').lower()}."

    return (
        f"📊 *This week*\n"
        f"• {week_approved} replies sent\n"
        f"• {queued} waiting in queue\n"
        f"• ₦{deposits_ngn:,.0f} deposits caught (lifetime)\n"
        f"• {streak}-day brief streak"
        f"{pause_line}"
    )


def _do_rescue(client: dict) -> str:
    """'Follow up everyone who asked price' — surface revivable conversations
    and point to the one-tap Revenue Rescue draft-all button.

    Deliberately does NOT auto-fire a draft campaign from a voice parse:
    HITL stays in charge. EYO reports the find; the owner taps to draft.
    """
    from services.money_leak import rescue_targets
    name = client.get("name", "")
    targets = rescue_targets(name, days=30)
    if not targets:
        return "Good news — no dead conversations to revive right now. Your pipeline's clean. 💪"

    n = len(targets)
    high = sum(1 for t in targets if t.get("reason") in ("ghosted_promises", "asked_price_no_quote"))

    token = client.get("portal_token")
    link = ""
    if token:
        try:
            base = (get_settings().app_base_url or "").rstrip("/")
        except Exception:
            base = ""
        link = f"\nTap to review + draft all: {base}/portal/{token}/money-leak"

    high_line = f" — {high} look high-intent" if high else ""
    return (
        f"Found {n} conversation{'s' if n != 1 else ''} where money went quiet{high_line}. "
        f"I can draft a follow-up for each — they'll land in your approval queue, "
        f"nothing sends till you tap approve.{link}"
    )


def _do_stub(action: str) -> str:
    pretty = {
        "set_rule":       "rule update",
        "update_pricing": "pricing update",
        "bulk_approve":   "bulk approve",
    }.get(action, action)
    return (f"Noted — *{pretty}* commands are in beta. "
            f"Yori will action this manually within the hour.")


async def handle_owner_command(
    client_doc: dict,
    sender_phone: str,
    transcript: str,
) -> Optional[dict]:
    """
    Try to handle the message as an owner command. Returns a dict with
    {handled: bool, action, confirmation} if we acted, else None to fall
    through to the normal drafter flow.
    """
    if not match_owner(sender_phone, client_doc):
        return None
    if not (transcript or "").strip():
        return None

    intent = await parse_intent(transcript)
    action = intent["action"]
    if action == "none" or intent["confidence"] < 0.6:
        return None

    try:
        if action == "pause":
            confirmation = _do_pause(client_doc, intent["params"].get("hours", 12))
        elif action == "resume":
            confirmation = _do_resume(client_doc)
        elif action == "status_check":
            confirmation = _do_status(client_doc)
        elif action == "rescue_followup":
            confirmation = _do_rescue(client_doc)
        elif action in ("set_rule", "update_pricing", "bulk_approve"):
            confirmation = _do_stub(action)
        else:
            return None
    except Exception as e:
        log.error("owner_voice_execute_failed", error=str(e), action=action)
        return None

    # Send confirmation via THIS client's own WhatsApp account
    try:
        from tools.outreach import send_whatsapp_for_client
        await send_whatsapp_for_client(
            phone=_norm_phone(sender_phone) or sender_phone,
            message=confirmation,
            client_doc=client_doc,
        )
    except Exception as e:
        log.error("owner_voice_confirm_send_failed", error=str(e))

    # PostHog
    try:
        from services.analytics import track
        track("owner_voice_command",
              distinct_id=f"client:{client_doc.get('name','')}",
              action=action,
              confidence=intent["confidence"],
              transcript_chars=len(transcript))
    except Exception:
        pass

    log.info("owner_voice_command_handled",
             client=client_doc.get("name"),
             action=action, confidence=intent["confidence"])

    return {"handled": True, "action": action, "confirmation": confirmation}
