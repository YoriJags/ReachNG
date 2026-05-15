"""
Predictive Co-pilot — the operator chats with their AI agent in plain English.

The architectural choice: Haiku as a router, Mongo as the data plane. The owner
asks "who hasn't replied in 5 days?" — Haiku picks the right tool name + args,
we run a deterministic Mongo query, then a second short Haiku call narrates the
result. Plain language in, plain language out, with the actual numbers grounded
in real data (no hallucination because the query is deterministic).

Cost per ask: ~₦8 (₦4 planner + ₦4 narrator). Will be metered by T0.2.5 once
that ships.

Scope: every call REQUIRES `client_id` (operator picks which client they're
asking about). Cross-client questions are not supported in v1 — protects
isolation guarantees we shipped earlier.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog
from bson import ObjectId

from config import get_settings
from database import get_db

log = structlog.get_logger()


# ─── Errors ───────────────────────────────────────────────────────────────────

class CopilotScopeError(Exception):
    """Refuses calls without client_id — preserves multi-tenant isolation."""


# ─── Tool registry ────────────────────────────────────────────────────────────

TOOLS = {
    "quiet_leads": {
        "description": "List leads that have gone quiet — no inbound or outbound message in the last N days. "
                       "Use when the owner asks who hasn't replied, who needs a nudge, or who's gone cold.",
        "args": {"days": "int, default 7"},
    },
    "pending_approvals": {
        "description": "List drafts currently waiting in the owner's HITL approval queue. "
                       "Use when the owner asks what's pending, what needs my attention, "
                       "what's in the queue, or how many drafts are waiting.",
        "args": {},
    },
    "hot_leads": {
        "description": "Surface leads marked hot, on-fire, closing-stage, or escalated by the emotion classifier. "
                       "Use when the owner asks what's hot, who should I call, who's ready to buy, "
                       "what's urgent today.",
        "args": {},
    },
    "summarise_week": {
        "description": "Summarise the last 7 days of ₦ closed, bookings, hours saved, approval rate. "
                       "Use when the owner asks how the week went, what we did this week, "
                       "what the numbers look like.",
        "args": {},
    },
    "find_contact": {
        "description": "Find a specific contact by partial name or phone fragment. "
                       "Use when the owner names a person ('that Banana Island buyer', 'Mrs Adekoya', 'Tomi').",
        "args": {"query": "string — partial name or phone fragment"},
    },
}


# ─── Tool implementations (deterministic Mongo) ───────────────────────────────

def _tool_quiet_leads(client_id: str, args: dict) -> dict:
    days = int(args.get("days") or 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    db = get_db()
    # Closer leads where last thread activity is older than cutoff
    cursor = db["closer_leads"].find({
        "client_id": client_id,
        "stage":     {"$nin": ["booked", "lost"]},
        "$or": [
            {"updated_at": {"$lt": cutoff}},
            {"updated_at": {"$exists": False}},
        ],
    }, {"contact_name": 1, "contact_phone": 1, "stage": 1, "vertical": 1,
        "updated_at": 1, "inquiry_text": 1}).sort("updated_at", 1).limit(20)
    rows = list(cursor)
    return {
        "tool": "quiet_leads",
        "days": days,
        "count": len(rows),
        "leads": [{
            "name":     r.get("contact_name"),
            "phone":    r.get("contact_phone"),
            "stage":    r.get("stage"),
            "vertical": r.get("vertical"),
            "last_touch": r.get("updated_at").isoformat() if r.get("updated_at") else None,
            "first_message": (r.get("inquiry_text") or "")[:120],
        } for r in rows],
    }


def _tool_pending_approvals(client_id: str, args: dict) -> dict:
    db = get_db()
    # Look up client name to filter approvals (approvals are scoped by name today)
    client = db["clients"].find_one({"_id": ObjectId(client_id)}, {"name": 1})
    if not client:
        return {"tool": "pending_approvals", "count": 0, "drafts": []}
    name = client["name"]
    now = datetime.now(timezone.utc)
    rows = list(db["pending_approvals"].find({
        "client_name": name,
        "status":      "pending",
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }, {"contact_name": 1, "message": 1, "created_at": 1, "channel": 1,
        "classification": 1, "escalated": 1, "phone": 1, "source": 1})
        .sort("created_at", -1).limit(20))
    return {
        "tool": "pending_approvals",
        "count": len(rows),
        "drafts": [{
            "id":           str(r["_id"]),
            "contact":      r.get("contact_name"),
            "channel":      r.get("channel"),
            "source":       r.get("source"),
            "message":      (r.get("message") or "")[:200],
            "created_at":   r["created_at"].isoformat() if r.get("created_at") else None,
            "escalated":    bool(r.get("escalated")),
            "classification": r.get("classification"),
        } for r in rows],
    }


def _tool_hot_leads(client_id: str, args: dict) -> dict:
    db = get_db()
    client = db["clients"].find_one({"_id": ObjectId(client_id)}, {"name": 1})
    if not client:
        return {"tool": "hot_leads", "count": 0, "drafts": []}
    name = client["name"]
    # Hot = pending drafts that are escalated OR classified urgency in {hot, on_fire}
    # OR stage in {negotiating, closing}
    now = datetime.now(timezone.utc)
    base_q = {
        "client_name": name,
        "status":      "pending",
        "$or": [{"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
    }
    rows = list(db["pending_approvals"].find(base_q,
        {"contact_name": 1, "message": 1, "created_at": 1, "phone": 1,
         "escalated": 1, "classification": 1, "source": 1}))
    hot = []
    for r in rows:
        cls = r.get("classification") or {}
        if r.get("escalated") or cls.get("urgency") in {"hot", "on_fire"} \
                or cls.get("stage") in {"negotiating", "closing"}:
            hot.append({
                "id":      str(r["_id"]),
                "contact": r.get("contact_name"),
                "phone":   r.get("phone"),
                "message": (r.get("message") or "")[:200],
                "classification": cls,
                "escalated": bool(r.get("escalated")),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
    # Rank: escalated first, then on_fire, then hot, then negotiating, then closing
    rank = {"on_fire": 4, "hot": 3, "negotiating": 2, "closing": 1}
    hot.sort(key=lambda d: (
        1 if d["escalated"] else 0,
        rank.get((d.get("classification") or {}).get("urgency"), 0),
        rank.get((d.get("classification") or {}).get("stage"), 0),
    ), reverse=True)
    return {"tool": "hot_leads", "count": len(hot), "drafts": hot[:15]}


def _tool_summarise_week(client_id: str, args: dict) -> dict:
    try:
        from services.scorecard import compute_scorecard
        sc = compute_scorecard(client_id, period_days=7)
        return {"tool": "summarise_week", "scorecard": asdict(sc)}
    except Exception as e:
        log.warning("copilot_summarise_week_failed", error=str(e))
        return {"tool": "summarise_week", "scorecard": None, "error": str(e)}


def _tool_find_contact(client_id: str, args: dict) -> dict:
    q = (args.get("query") or "").strip()
    if not q:
        return {"tool": "find_contact", "query": "", "count": 0, "matches": []}
    db = get_db()
    client = db["clients"].find_one({"_id": ObjectId(client_id)}, {"name": 1})
    if not client:
        return {"tool": "find_contact", "query": q, "count": 0, "matches": []}
    name = client["name"]
    digits = re.sub(r"\D", "", q)
    # Match against closer_leads first (richest data)
    leads = list(db["closer_leads"].find({
        "client_id": client_id,
        "$or": [
            {"contact_name":  {"$regex": re.escape(q), "$options": "i"}},
            {"contact_phone": {"$regex": digits, "$options": "i"}} if digits else None,
        ],
    } if not digits else {
        "client_id": client_id,
        "$or": [
            {"contact_name":  {"$regex": re.escape(q), "$options": "i"}},
            {"contact_phone": {"$regex": digits, "$options": "i"}},
        ],
    }, {"contact_name": 1, "contact_phone": 1, "stage": 1, "inquiry_text": 1, "updated_at": 1}).limit(10))
    return {
        "tool": "find_contact",
        "query": q,
        "count": len(leads),
        "matches": [{
            "id":      str(l["_id"]),
            "name":    l.get("contact_name"),
            "phone":   l.get("contact_phone"),
            "stage":   l.get("stage"),
            "summary": (l.get("inquiry_text") or "")[:140],
            "last_touch": l["updated_at"].isoformat() if l.get("updated_at") else None,
        } for l in leads],
    }


TOOL_HANDLERS = {
    "quiet_leads":       _tool_quiet_leads,
    "pending_approvals": _tool_pending_approvals,
    "hot_leads":         _tool_hot_leads,
    "summarise_week":    _tool_summarise_week,
    "find_contact":      _tool_find_contact,
}


# ─── Planner (Haiku) ─────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """You are the routing brain for a Nigerian SME owner's AI co-pilot.
The owner asks a question in natural language about their business inbox.
Your only job is to pick the right tool to call and assemble its arguments.

Available tools (pick exactly ONE):
""" + "\n".join(
    f'  • "{name}" — {meta["description"]}'
    + (f" Args: {meta['args']}" if meta["args"] else " No args.")
    for name, meta in TOOLS.items()
) + """

Return ONLY a JSON object (no markdown, no preamble):
{"tool": "<tool_name>", "args": { ... }}

If the question doesn't fit any tool, return:
{"tool": "none", "args": {}, "reason": "<short reason>"}

Examples:
  Q: "Who hasn't replied to me in 5 days?"  → {"tool":"quiet_leads","args":{"days":5}}
  Q: "Who's hot today?"                      → {"tool":"hot_leads","args":{}}
  Q: "What's in my queue?"                   → {"tool":"pending_approvals","args":{}}
  Q: "How did this week go?"                 → {"tool":"summarise_week","args":{}}
  Q: "Find Mrs Adekoya"                      → {"tool":"find_contact","args":{"query":"Adekoya"}}
"""


def _plan(question: str) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"tool": "none", "args": {}, "reason": "ANTHROPIC_API_KEY missing"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=_PLANNER_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        log.warning("copilot_planner_failed", error=str(e))
        return {"tool": "none", "args": {}, "reason": f"planner error: {e}"}

    if raw.startswith("```"):
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
    try:
        plan = json.loads(raw)
    except Exception:
        return {"tool": "none", "args": {}, "reason": "could not parse planner JSON"}
    if plan.get("tool") not in TOOLS and plan.get("tool") != "none":
        return {"tool": "none", "args": {}, "reason": f"unknown tool: {plan.get('tool')}"}
    plan["args"] = plan.get("args") or {}
    return plan


# ─── Narrator (Haiku) — turns data into plain English ─────────────────────────

_NARRATOR_SYSTEM = """You are the voice of a Lagos SME owner's AI co-pilot.

You will be given:
  • The owner's original question
  • The structured data your tool returned

Write a SHORT, plain-English answer (3-6 sentences, no markdown).
- Be concrete: cite names, naira amounts, days.
- Don't list every record — surface the top 3-5 by relevance.
- If the result is empty, say so warmly ("Nothing in the queue — quiet morning.").
- Never invent facts. Only use what's in the data.
- Sound like a sharp colleague, not a chatbot. No emoji unless data carries one.
- End with the obvious next action if there is one ("Tap to review them in the queue.").
"""


def _narrate(question: str, tool_result: dict) -> str:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return "Result loaded — open the dashboard panel to see details."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # Trim heavy payloads so the narrator stays cheap
        trimmed = _trim_for_narrator(tool_result)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_NARRATOR_SYSTEM,
            messages=[{"role": "user", "content":
                f"Question: {question}\n\nTool result (JSON):\n{json.dumps(trimmed, default=str)[:3500]}"}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return text or "—"
    except Exception as e:
        log.warning("copilot_narrator_failed", error=str(e))
        return "Result loaded — open the dashboard panel to see details."


def _trim_for_narrator(result: dict) -> dict:
    """Keep payloads under ~3.5KB by truncating message texts and lists."""
    t = dict(result)
    for key in ("leads", "drafts", "matches"):
        if isinstance(t.get(key), list):
            t[key] = t[key][:8]
            for row in t[key]:
                for f in ("message", "summary", "first_message"):
                    if f in row and isinstance(row[f], str):
                        row[f] = row[f][:120]
    return t


# ─── Public entry point ──────────────────────────────────────────────────────

def ask(*, client_id: str, question: str) -> dict:
    """Plan → execute → narrate. Always scope-locked to client_id."""
    if not client_id or not str(client_id).strip():
        raise CopilotScopeError("copilot.ask requires client_id")
    cid = str(client_id).strip()
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "empty question"}

    plan = _plan(q)
    tool_name = plan.get("tool")
    if tool_name == "none" or tool_name not in TOOL_HANDLERS:
        return {
            "ok":       True,
            "tool":     "none",
            "reason":   plan.get("reason") or "Not sure how to answer that yet.",
            "narration": (
                "I can answer questions about quiet leads, pending approvals, hot leads, "
                "this week's numbers, or find a contact by name. Try: "
                "'who hasn't replied in 5 days?' or 'what's hot today?'."
            ),
        }

    try:
        result = TOOL_HANDLERS[tool_name](cid, plan.get("args") or {})
    except Exception as e:
        log.error("copilot_tool_exec_failed", tool=tool_name, error=str(e))
        return {"ok": False, "tool": tool_name, "error": str(e)}

    narration = _narrate(q, result)
    log.info("copilot_ask", client_id=cid, tool=tool_name)
    return {
        "ok":        True,
        "tool":      tool_name,
        "args":      plan.get("args") or {},
        "result":    result,
        "narration": narration,
    }
