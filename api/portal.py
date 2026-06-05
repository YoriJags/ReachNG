"""
Client Portal — token-gated read-only dashboard for each paying ReachNG client.
Each client gets a unique URL: /portal/{token}
Shows their contacts, outreach stats, and ROI.
"""
import re
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from bson import ObjectId
from database import get_contacts, get_outreach_log, get_db
from tools.roi import get_roi_summary
from auth import require_auth as _require_admin_auth

router = APIRouter(prefix="/portal", tags=["Portal"])


def get_clients():
    return get_db()["clients"]


# ─── Token management ─────────────────────────────────────────────────────────

def generate_portal_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_client_token(client_name: str) -> str:
    """Generate and store a portal token if the client doesn't have one yet."""
    clients = get_clients()
    client = clients.find_one({"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}})
    if not client:
        raise ValueError(f"Client '{client_name}' not found")
    if client.get("portal_token"):
        return client["portal_token"]
    token = generate_portal_token()
    clients.update_one(
        {"_id": client["_id"]},
        {"$set": {"portal_token": token, "portal_created_at": datetime.now(timezone.utc)}},
    )
    return token


def _get_client_by_token(token: str) -> dict | None:
    return get_clients().find_one({"portal_token": token, "active": True})


# ─── API endpoints ────────────────────────────────────────────────────────────

@router.post("/generate/{client_name}")
async def generate_portal_link(client_name: str, _: str = Depends(_require_admin_auth)):
    """Generate (or return existing) portal token for a client. Requires Basic Auth."""
    try:
        token = ensure_client_token(client_name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "client": client_name,
        "portal_token": token,
        "portal_url": f"/portal/{token}",
    }


@router.get("/data/{token}")
async def get_portal_data(token: str):
    """JSON data endpoint for the portal — used by the HTML dashboard."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    vertical = client.get("vertical")
    client_name = client["name"]

    # Contacts scoped to this client only — prevents cross-client data leak
    contacts = list(
        get_contacts()
        .find({"vertical": vertical, "client_name": client_name})
        .sort("lead_score", -1)
        .limit(100)
    )
    for c in contacts:
        c["id"] = str(c.pop("_id"))
        for f in ("created_at", "last_contacted_at", "updated_at", "next_followup_at"):
            if hasattr(c.get(f), "isoformat"):
                c[f] = c[f].isoformat()

    # Status counts — scoped to this client only
    from tools.memory import get_pipeline_stats
    stats = get_pipeline_stats(vertical=vertical, client_name=client_name)

    # ROI
    roi = get_roi_summary(days=30, client_name=client_name)

    # Cash signals — Owner Brief headline data
    try:
        from tools.cash_signals import cash_signals_for
        cash = cash_signals_for(client_name)
    except Exception:
        cash = None

    return {
        "client": {
            "name":       client_name,
            "vertical":   vertical,
            "agent_name": client.get("agent_name") or "EYO",
        },
        # Legacy flat keys preserved for older portal JS that reads them directly
        "vertical": vertical,
        "stats": stats,
        "roi": roi,
        "cash": cash,
        "contacts": contacts,
        "autopilot": client.get("autopilot", False),
        "holding_message": client.get("holding_message", ""),
    }


@router.post("/{token}/agent-name")
async def update_agent_name(token: str, payload: dict):
    """Client-facing: rename the agent. Default is 'EYO'. 1-20 chars."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    name = (payload.get("agent_name") or "").strip()
    if not (1 <= len(name) <= 20):
        raise HTTPException(400, "agent_name must be 1-20 characters")
    get_clients().update_one(
        {"_id": client["_id"]},
        {"$set": {"agent_name": name, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True, "agent_name": name}


@router.get("/journey/{token}")
async def get_customer_journey(token: str, phone: str, limit: int = 200):
    """Full timeline for one customer phone — inbounds, transcripts, drafts,
    approvals, outbounds, receipts matched, facts extracted, stage changes.

    The single best 'wow' surface for the per-customer memory layer.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    if not phone or len(phone) < 5:
        raise HTTPException(400, "phone required")

    from database import get_db
    db = get_db()
    cid = str(client["_id"])
    cname = client["name"]

    events: list[dict] = []

    def _add(ts, kind: str, body: str, meta: dict | None = None):
        if not ts:
            return
        try:
            iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        except Exception:
            return
        events.append({"at": iso, "kind": kind, "body": body[:600] if body else "",
                        "meta": meta or {}})

    # 1) Inbound messages
    try:
        for m in db["inbound_messages"].find(
            {"client_name": cname, "sender_phone": phone},
            {"received_at": 1, "body": 1, "voice_transcript": 1, "media_type": 1},
        ).sort("received_at", -1).limit(limit):
            kind = "voice_in" if m.get("voice_transcript") else "msg_in"
            body = m.get("voice_transcript") or m.get("body") or ""
            _add(m.get("received_at"), kind, body,
                  {"media_type": m.get("media_type")})
    except Exception:
        pass

    # 2) Drafts queued + their resolution
    try:
        for a in db["pending_approvals"].find(
            {"client_name": cname, "phone": phone},
            {"created_at": 1, "actioned_at": 1, "status": 1, "message": 1,
             "edited_message": 1, "risk": 1, "classification": 1},
        ).sort("created_at", -1).limit(limit):
            _add(a.get("created_at"), "draft_queued",
                  (a.get("message") or "")[:600],
                  {"risk": a.get("risk"), "classification": a.get("classification")})
            if a.get("actioned_at"):
                _add(a.get("actioned_at"), f"draft_{a.get('status','actioned')}",
                      (a.get("edited_message") or a.get("message") or "")[:600],
                      {"status": a.get("status")})
    except Exception:
        pass

    # 3) Outbound sends
    try:
        for o in db["outreach_log"].find(
            {"client_name": cname, "phone": phone},
            {"sent_at": 1, "message": 1, "channel": 1},
        ).sort("sent_at", -1).limit(limit):
            _add(o.get("sent_at"), "msg_out", o.get("message") or "",
                  {"channel": o.get("channel")})
    except Exception:
        pass

    # 4) Receipts matched
    try:
        for r in db["receipt_matches"].find(
            {"client_name": cname, "contact_phone": phone},
            {"matched_at": 1, "receipt": 1, "match_kind": 1, "amount_ngn": 1},
        ).sort("matched_at", -1).limit(limit):
            amt = r.get("amount_ngn") or (r.get("receipt") or {}).get("amount_ngn")
            _add(r.get("matched_at"), "receipt_matched",
                  f"₦{amt:,.0f} via {(r.get('receipt') or {}).get('bank','?')}" if amt else "Receipt",
                  {"match_kind": r.get("match_kind"), "amount_ngn": amt})
    except Exception:
        pass

    # 5) Facts extracted (memory)
    try:
        for f in db["client_memory"].find(
            {"client_id": cid, "contact_phone": phone},
            {"created_at": 1, "fact_type": 1, "value": 1, "source": 1},
        ).sort("created_at", -1).limit(limit):
            _add(f.get("created_at"), "fact_extracted",
                  f"{f.get('fact_type')}: {f.get('value')}",
                  {"source": f.get("source")})
    except Exception:
        pass

    # 6) Closer stage changes
    try:
        lead = db["closer_leads"].find_one(
            {"client_id": cid, "contact_phone": phone},
            {"thread": 1, "stage": 1, "created_at": 1},
        )
        if lead:
            _add(lead.get("created_at"), "lead_opened",
                  f"Stage: {lead.get('stage','new')}",
                  {"stage": lead.get("stage")})
            for ev in (lead.get("thread") or []):
                if ev.get("direction") == "note":
                    _add(ev.get("at"), "operator_note", ev.get("body") or "",
                          {"author": ev.get("author")})
    except Exception:
        pass

    # Sort newest first
    events.sort(key=lambda e: e["at"], reverse=True)
    events = events[:limit]

    # Lightweight rollup
    rollup = {
        "events_total":      len(events),
        "first_seen":        events[-1]["at"] if events else None,
        "last_seen":         events[0]["at"]  if events else None,
        "drafts_queued":     sum(1 for e in events if e["kind"] == "draft_queued"),
        "msgs_in":           sum(1 for e in events if e["kind"] in ("msg_in", "voice_in")),
        "msgs_out":          sum(1 for e in events if e["kind"] == "msg_out"),
        "receipts_matched":  sum(1 for e in events if e["kind"] == "receipt_matched"),
        "facts_known":       sum(1 for e in events if e["kind"] == "fact_extracted"),
    }
    return {"client": cname, "phone": phone, "rollup": rollup, "events": events}


@router.get("/share-card/{token}")
async def get_share_card(token: str, period: str = "this month"):
    """Render the owner's ROI share card as a 1200x630 PNG.

    Pulled from the live scorecard so we never invent numbers. Owner taps,
    saves, posts to IG/X.
    """
    from fastapi.responses import Response
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    naira = 0
    hours = 0.0
    bookings = 0
    try:
        from services.scorecard import compute_scorecard
        sc = compute_scorecard(client_id=str(client["_id"]), period_days=30)
        # compute_scorecard returns a dataclass / pydantic-ish object
        d = sc.model_dump() if hasattr(sc, "model_dump") else (sc if isinstance(sc, dict) else sc.__dict__)
        naira    = int((d.get("naira_closed_via_reachng") or 0)
                       + (d.get("naira_recovered_chase")  or 0))
        hours    = float(d.get("hours_saved") or 0)
        bookings = int(d.get("bookings_confirmed") or 0)
    except Exception:
        pass

    from services.roi_card import render_roi_card
    png = render_roi_card(
        business_name=client["name"],
        naira_tracked=naira,
        hours_saved=hours,
        bookings=bookings,
        period_label=period,
        agent_name=client.get("agent_name") or "EYO",
    )
    return Response(content=png, media_type="image/png",
                    headers={"Content-Disposition": 'inline; filename="eyo-share-card.png"'})


@router.get("/almost-lost/{token}")
async def get_almost_lost(token: str, hours: int = 24):
    """Drafts that expired without being approved + recent inbounds with no
    outbound reply within the after-hours window.

    Sells autopilot internally — the owner sees what they almost let slip.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    from database import get_db
    db = get_db()
    cname = client["name"]
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=max(1, min(168, hours)))

    # 1) Expired drafts that were never approved
    expired = list(db["pending_approvals"].find(
        {"client_name": cname,
         "status": "pending",
         "expires_at": {"$lt": now, "$gt": since}},
        {"contact_name": 1, "phone": 1, "message": 1, "created_at": 1,
         "expires_at": 1, "risk": 1, "classification": 1},
    ).sort("expires_at", -1).limit(20))

    # 2) Inbound messages older than 4 hours with no outbound to that phone
    inbound_col = db.get_collection("inbound_messages")
    silent = []
    if inbound_col is not None:
        cutoff = now - timedelta(hours=4)
        cursor = inbound_col.find(
            {"client_name": cname,
             "received_at": {"$gte": since, "$lt": cutoff}},
            {"sender_phone": 1, "body": 1, "received_at": 1, "contact_name": 1},
        ).sort("received_at", -1).limit(40)
        seen_phones: set[str] = set()
        for m in cursor:
            phone = m.get("sender_phone") or ""
            if not phone or phone in seen_phones:
                continue
            seen_phones.add(phone)
            # Was anything sent back to this phone since the inbound?
            replied = db["outreach_log"].find_one(
                {"client_name": cname, "phone": phone,
                 "sent_at": {"$gte": m["received_at"]}},
                {"_id": 1},
            )
            if replied:
                continue
            silent.append({
                "contact_name":  m.get("contact_name") or "Unknown",
                "phone":         phone,
                "received_at":   m["received_at"].isoformat() if hasattr(m["received_at"], "isoformat") else m["received_at"],
                "preview":       (m.get("body") or "")[:140],
                "hours_silent":  round((now - m["received_at"]).total_seconds() / 3600, 1),
            })
            if len(silent) >= 10:
                break

    out_expired = [{
        "contact_name": d.get("contact_name") or "Unknown",
        "phone":        d.get("phone"),
        "preview":      (d.get("message") or "")[:140],
        "expired_at":   d["expires_at"].isoformat() if d.get("expires_at") and hasattr(d["expires_at"], "isoformat") else d.get("expires_at"),
        "confidence":   ((d.get("risk") or {}).get("confidence")),
        "urgency":      ((d.get("classification") or {}).get("urgency")),
    } for d in expired]

    return {
        "client":       cname,
        "window_hours": hours,
        "expired":      out_expired,
        "silent":       silent,
        "totals":       {"expired": len(out_expired), "silent": len(silent)},
    }


@router.get("/missed-opportunities/{token}")
async def get_missed_opportunities(token: str, days: int = 30):
    """List of leads who asked for price but never got a quote — Radar v1."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from tools.cash_signals import missed_opportunities_for
    return {
        "client": client["name"],
        "days": days,
        "missed": missed_opportunities_for(client["name"], days=days),
    }


@router.get("/owner-brief/{token}")
async def get_owner_brief(token: str):
    """
    Cash-focused Owner Brief payload — what the portal renders as today's
    money headline. Same numbers the 8am WhatsApp brief uses.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from tools.cash_signals import cash_signals_for
    from tools.morning_brief_client import compile_client_brief
    name = client["name"]
    return {
        "client": name,
        "cash": cash_signals_for(name),
        "whatsapp_preview": compile_client_brief(name, portal_url=f"/portal/{token}"),
    }


@router.get("/sales-copilot/{token}")
async def get_sales_copilot(token: str, days: int = 14):
    """Pipeline-card view of inbound threads that need a next move."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from tools.sales_copilot import sales_copilot_for
    return {
        "client": client["name"],
        "days": days,
        **sales_copilot_for(client["name"], days=days),
    }


# ─── Magic-potion feature endpoints ──────────────────────────────────────────
# Route convention for these NEW features (so future UI work isn't confused):
#   • HTML pages : GET /portal/{token}/<feature>        (matches /{token}/vault)
#   • JSON data  : GET /portal/{token}/<feature>/data   (or /{token}/<feature>
#                  when there is no page). All token-first.
# (The older owner-brief/{token}, missed-opportunities/{token}, almost-lost/{token}
#  data endpoints predate this and use /verb/{token}; left as-is to avoid breaking
#  anything already pointing at them.)

@router.get("/{token}/money-leak", response_class=HTMLResponse)
async def money_leak_page(token: str, request: Request):
    """Renders the Money Leak Report. Pre-paywall hook: show the leak first,
    ask for payment second."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.money_leak import money_leak_report
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal/money_leak.html", {
        "token":       token,
        "client_name": client.get("name", "your business"),
        "report":      money_leak_report(client["name"]),
    })


@router.get("/{token}/money-leak/data")
async def get_money_leak(token: str, days: int = 30):
    """Money Leak Report payload — 'You have ₦X sitting in dead chats.'

    Composes confirmed-owed (ledgers) + asked-price-no-quote + ghosted
    pay-promises + silent inbound into one ₦ figure with examples.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.money_leak import money_leak_report
    return money_leak_report(client["name"], days=max(1, min(180, days)))


@router.get("/{token}/demand-radar/data")
async def get_demand_radar(token: str, days: int = 30):
    """EYO Radar — what the market keeps asking for, aggregated from inbound.

    Flag-gated (off by default). Returns ranked demand topics + honest owner
    lines ('N people asked the price of X this week'). Empty until the radar
    flag is on and signals accumulate.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    name = client["name"]
    from services.eyo_flags import eyo_enabled
    if not eyo_enabled(name, "radar"):
        return {"client": name, "enabled": False, "signals": [], "headlines": []}

    from services.demand_intel import radar_for_client
    days = max(1, min(180, days))
    radar = radar_for_client(name, days=days)
    lines = []
    for s in radar.get("signals", []):
        n = s["price_asks"] or s["mentions"]
        who = "person" if n == 1 else "people"
        verb = "asked the price of" if s["price_asks"] else "asked about"
        lines.append(f"{n} {who} {verb} {s['display']} in the last {days} days.")
    return {"client": name, "enabled": True, "days": days, "headlines": lines, **radar}


@router.get("/{token}/cashflow/data")
async def get_cashflow(token: str, days: int = 30):
    """EYO Cashflow — this week's likely collections + what's stuck + who to nudge.

    Flag-gated (off by default). Built from the real per-lead money-leak numbers,
    clearly an estimate. Foreign quotes ride along separately, never in expected.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    name = client["name"]
    from services.eyo_flags import eyo_enabled
    if not eyo_enabled(name, "cashflow"):
        return {"client": name, "enabled": False}

    from services.cashflow_brief import cashflow_for_client
    from services.cashflow import cashflow_summary_text
    forecast = cashflow_for_client(name, days=max(1, min(180, days)))
    return {"client": name, "enabled": True,
            "summary": cashflow_summary_text(forecast), **forecast}


@router.get("/{token}/revenue-rescue")
async def get_revenue_rescue(token: str, days: int = 30):
    """'Find cash this week' — prioritised, de-duplicated follow-up targets
    plus the leak headline. The page's draft-all button reuses
    POST /run-resurrection/{token} (HITL-forced)."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.money_leak import money_leak_report, rescue_targets
    days = max(1, min(180, days))
    report = money_leak_report(client["name"], days=days)
    return {
        "client":        client["name"],
        "headline":      report["headline"],
        "total_ngn":     report["total_ngn"],
        "confirmed_ngn": report["confirmed_ngn"],
        "pipeline_ngn":  report["pipeline_ngn"],
        "targets":       rescue_targets(client["name"], days=days),
    }


@router.get("/{token}/speed-watch")
async def get_speed_watch(token: str, days: int = 30):
    """Competitor Speed Watch — your median response time vs your category."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.speed_watch import response_speed_for
    return response_speed_for(client["name"], days=days, vertical=client.get("vertical"))


@router.get("/{token}/readiness")
async def get_readiness(token: str):
    """Autopilot Readiness Score with the 4-dimension breakdown
    (tone / price / escalation / payment)."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.autopilot import readiness_breakdown
    return readiness_breakdown(client["name"])


@router.get("/{token}/payments")
async def get_payments(token: str, days: int = 30):
    """Payments & receipts feed — confirmed receipts + Paystack charges."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.portal_feeds import payments_for
    return payments_for(client["name"], str(client["_id"]), days=max(1, min(180, days)))


@router.get("/{token}/bookings")
async def get_bookings(token: str, days: int = 30):
    """Bookings/deals the client marked closed."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.portal_feeds import bookings_for
    return bookings_for(client["name"], days=max(1, min(180, days)))


@router.get("/{token}/savings")
async def get_savings(token: str, days: int = 30):
    """Estimated hours + ₦ saved from messages EYO handled."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.portal_feeds import savings_for
    return savings_for(client["name"], days=max(1, min(180, days)))


@router.get("/{token}/recap")
async def get_recap(token: str, days: int = 1):
    """'What EYO did since yesterday' — compact recap for the Today tab."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.portal_feeds import recap_for
    return recap_for(client["name"], days=max(1, min(7, days)))


@router.get("/{token}/brief-history")
async def get_brief_history(token: str):
    """Owner Brief send history + current streak."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from services.portal_feeds import brief_history_for
    return brief_history_for(client["name"])


@router.get("/{token}/report.pdf")
async def get_report_pdf(token: str, days: int = 30):
    """One-page PDF results report."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    from fastapi import Response
    from services.portal_feeds import report_pdf_bytes
    pdf = report_pdf_bytes(client["name"], str(client["_id"]), days=max(1, min(180, days)))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=reachng-report.pdf"})


# ─── Lead Resurrection (token-auth wrapper around /b2c upload + run) ─────────

@router.get("/upload-leads/{token}", response_class=HTMLResponse)
async def upload_leads_page(token: str, request: Request):
    """Lead Resurrection — upload an old CSV of leads, agent revives them."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")
    templates = request.app.state.templates
    # Recent imports for this client — shows the resurrection history
    imports = list(
        get_db()["lead_imports"]
        .find({"client_name": client["name"]}, {"_id": 0})
        .sort("uploaded_at", -1)
        .limit(10)
    )
    for im in imports:
        if hasattr(im.get("uploaded_at"), "isoformat"):
            im["uploaded_at"] = im["uploaded_at"].isoformat()
    return templates.TemplateResponse(
        request,
        "portal_upload_leads.html",
        {
            "token": token,
            "client_name": client["name"],
            "vertical": client.get("vertical") or "general",
            "imports": imports,
        },
    )


@router.post("/upload-leads/{token}")
async def upload_leads_submit(
    token: str,
    request: Request,
):
    """Portal-authenticated Lead Resurrection upload.

    Wraps tools.csv_import.parse_and_import_csv with the same NDPR
    consent guard as the admin /b2c/upload endpoint, but auth is by
    portal token instead of admin basic-auth.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    from fastapi import UploadFile
    from tools.csv_import import parse_and_import_csv
    from api.b2c import _record_import, _enforce_byo_enabled, _MAX_CSV_BYTES

    form = await request.form()
    file = form.get("file")
    consent = str(form.get("consent_attestation", "")).lower() in ("true", "on", "1", "yes")
    campaign_tag = form.get("campaign_tag") or "lead_resurrection"

    if not consent:
        raise HTTPException(
            422,
            "Consent attestation required. Tick the box confirming every contact "
            "in the file has a lawful basis under NDPR.",
        )
    if not isinstance(file, UploadFile) or not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV too large. Max {_MAX_CSV_BYTES // 1024}KB.")
    if not content:
        raise HTTPException(400, "Empty file")

    _enforce_byo_enabled(client)

    vertical = client.get("vertical") or "general"
    try:
        stats = parse_and_import_csv(
            csv_bytes=content,
            client_name=client["name"],
            vertical=vertical,
            campaign_tag=campaign_tag,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    import_id = _record_import(
        client_doc=client,
        filename=file.filename,
        file_bytes=content,
        consent_attestation=True,
        uploader=f"portal:{client['name']}",
        request=request,
        stats=stats,
        vertical=vertical,
        campaign_tag=campaign_tag,
    )

    return {
        "success": True,
        "client": client["name"],
        "vertical": vertical,
        "import_id": import_id,
        "campaign_tag": campaign_tag,
        **stats,
    }


@router.post("/run-resurrection/{token}")
async def run_resurrection(token: str, request: Request):
    """Trigger a Lead Resurrection campaign on uploaded leads.

    HITL mode is forced ON — every revival message lands in the approval
    queue so the owner sees what's about to go out before any of it sends.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
    max_contacts = max(1, min(200, int(body.get("max_contacts", 50))))
    dry_run = bool(body.get("dry_run", True))

    from api.b2c import run_b2c_campaign, RunB2CRequest
    from fastapi import BackgroundTasks
    payload = RunB2CRequest(
        vertical=client.get("vertical") or "general",
        max_contacts=max_contacts,
        dry_run=dry_run,
        hitl_mode=True,
    )
    return await run_b2c_campaign(
        client_name=client["name"],
        body=payload,
        background_tasks=BackgroundTasks(),
    )


@router.get("/demo", response_class=HTMLResponse)
async def demo_portal(request: Request):
    """Public demo — 90-second guided product tour.

    Phone-first cinematic walk-through (voice note → EYO draft → receipt
    catcher → owner brief → dashboard reveal). Cold prospects land here.
    Direct dashboard view available at /portal/demo/dashboard.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_demo_guided.html", {"vertical": "hospitality"})


@router.get("/demo/dashboard", response_class=HTMLResponse)
async def demo_portal_dashboard(request: Request, embed: int = 0):
    """Prospect-facing EYO Control Room — cream/sienna design matching the
    guided tour. Linked from Scene 5 'Open the Control Room'. Defaults to
    hospitality. Pass ?embed=1 for iframe rendering (hides chrome).
    """
    from services.demo_datasets import get_dataset, get_control_room
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_control_room.html",
        {"data": get_dataset(None), "cr": get_control_room(None),
         "vertical": "hospitality", "embed": bool(embed)})


@router.get("/demo/eyo", response_class=HTMLResponse)
async def demo_portal_eyo(request: Request):
    """Preview the REAL refactored client portal (portal.html) with sample data.

    Renders the production client IA in demo mode (a fetch-shim in the template
    serves believable sample data), so the redesigned dashboard can be reviewed
    without a live client or token. Registered before /demo/{vertical} so "eyo"
    is not matched as a vertical.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal.html", {
        "token":              "demo",
        "client_name":        "Altitude Lagos",
        "vertical":           "Hospitality",
        "whatsapp_connected": True,
        "whatsapp_health":    "OK",
        "onboarded":          True,
        "demo":               True,
    })


@router.get("/demo/{vertical}", response_class=HTMLResponse)
async def demo_portal_vertical(vertical: str, request: Request, embed: int = 0):
    """Vertical-specific EYO Control Room sample. Same prospect-facing
    cream/sienna design, vertical-tailored sample data. Only renders for
    verticals with real datasets — otherwise redirects to the guided tour.
    """
    from services.demo_datasets import get_dataset, list_verticals, get_control_room
    if vertical.lower() not in list_verticals():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/portal/demo", status_code=307)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_control_room.html",
        {"data": get_dataset(vertical), "cr": get_control_room(vertical),
         "vertical": vertical.lower(), "embed": bool(embed)})


@router.get("/demo/operator/raw", response_class=HTMLResponse)
async def demo_portal_operator_raw(request: Request):
    """Dark operator-view dashboard preserved for internal reference and
    for clients who want to see the production UI. Not linked from the
    public funnel.
    """
    from services.demo_datasets import get_dataset
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_demo.html",
        {"data": get_dataset(None), "vertical": "hospitality", "embed": False})


@router.get("/{token}", response_class=HTMLResponse)
async def client_portal(token: str, request: Request):
    """Render the client portal HTML dashboard.

    Real-estate clients are routed to the EstateOS landlord portal.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")

    client_name = client["name"]
    vertical_raw = client.get("vertical", "")

    if vertical_raw == "real_estate":
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/portal/estate/{token}", status_code=307)

    vertical = vertical_raw.replace("_", " ").title()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal.html", {
        "token":              token,
        "client_name":        client_name,
        "vertical":           vertical,
        "whatsapp_connected": bool(client.get("whatsapp_account_id")),
        "whatsapp_health":    client.get("whatsapp_health"),
        "onboarded":          bool(client.get("onboarded_at")),
    })


# ─── Client Book Onboarding v1 (SPRINT 2 #9 — slim slice) ──────────────────

@router.get("/{token}/book", response_class=HTMLResponse)
async def book_page(token: str, request: Request):
    """Render the customer-book upload page."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    from services.book_import import list_imports, book_summary
    cid = str(client["_id"])
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_book.html", {
        "token":       token,
        "client_name": client["name"],
        "imports":     list_imports(cid, limit=10),
        "summary":     book_summary(cid),
    })


@router.post("/{token}/book/upload-vcf")
async def book_upload_vcf(token: str, request: Request):
    """Accept a .vcf file upload + persist parsed contacts."""
    from fastapi import UploadFile
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    form = await request.form()
    upload = form.get("file")
    if not upload or not hasattr(upload, "read"):
        raise HTTPException(400, "No file uploaded")
    raw_bytes = await upload.read()
    if len(raw_bytes) > 2_000_000:  # 2MB cap
        raise HTTPException(413, "File too large (max 2MB)")
    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception:
        raise HTTPException(400, "Could not read file as text")
    from services.book_import import parse_vcf, import_book
    contacts = parse_vcf(text)
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None))
    result = import_book(
        client_id=str(client["_id"]),
        contacts=contacts,
        source="vcf",
        filename=getattr(upload, "filename", None),
        raw_chars=len(text),
        uploader_ip=ip,
    )
    return result


@router.post("/{token}/book/paste")
async def book_paste(token: str, request: Request):
    """Accept pasted text + parse + persist."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    body = await request.json()
    text = (body.get("text") or "").strip()
    if len(text) < 8:
        raise HTTPException(400, "Paste at least one contact (name + phone or email)")
    if len(text) > 200_000:
        raise HTTPException(413, "Paste too large (max 200k chars)")
    from services.book_import import parse_paste, import_book
    contacts = parse_paste(text)
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None))
    result = import_book(
        client_id=str(client["_id"]),
        contacts=contacts,
        source="paste",
        filename=None,
        raw_chars=len(text),
        uploader_ip=ip,
    )
    return result


# ─── EYO Vault (SPRINT 2 #6) ────────────────────────────────────────────────

@router.get("/{token}/vault", response_class=HTMLResponse)
async def vault_page(token: str, request: Request):
    """Render the per-customer memory dossier — switching-cost moat made visible."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_vault.html", {
        "token":       token,
        "client_name": client["name"],
        "vertical":    (client.get("vertical") or "").replace("_", " ").title(),
    })


@router.get("/{token}/vault/customers")
async def vault_list(token: str, search: str | None = None, limit: int = 200):
    """JSON list of customers with rollup (fact_count, last_seen, lifetime_ngn)."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    from services.vault import list_customers
    rows = list_customers(str(client["_id"]), limit=limit, search=search)
    # Serialise datetimes
    for r in rows:
        for k in ("last_seen_at", "first_seen_at"):
            v = r.get(k)
            if v: r[k] = v.isoformat()
    return {"customers": rows, "count": len(rows)}


@router.get("/{token}/vault/customer")
async def vault_customer(token: str, phone: str):
    """JSON dossier for one customer — full facts grouped by type + spend."""
    if not phone:
        raise HTTPException(400, "phone required")
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    from services.vault import get_customer
    dossier = get_customer(str(client["_id"]), phone)
    # Serialise datetimes
    def _ser(d):
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d
    _ser(dossier)
    for facts in dossier.get("facts_by_type", {}).values():
        for f in facts: _ser(f)
    for f in dossier.get("facts", []): _ser(f)
    return dossier


@router.get("/{token}/configure", response_class=HTMLResponse)
async def configure_page(token: str, request: Request):
    """Client-facing AI Configuration page — KB upload, Rules, Scenarios, Sandbox.

    Single dedicated page (not embedded in portal.html) so the config UX has room
    to breathe and so existing portal layouts don't risk breakage.
    """
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "portal_configure.html",
        {
            "token":       token,
            "client_name": client["name"],
            "vertical":    client.get("vertical") or "general",
        },
    )


# ─── Portal HTML ──────────────────────────────────────────────────────────────

def _portal_html(token: str, client_name: str, vertical: str, demo: bool = False) -> str:
    data_loader = "const data = DEMO_DATA;" if demo else f"const data = await fetch('/portal/data/{token}').then(r => r.json());"
    demo_banner = '<p style="background:#1a1000;color:#f5c842;font-size:11px;padding:8px 16px;margin-bottom:24px;border:1px solid #f5c842;letter-spacing:0.1em;">DEMO — Sample data for illustration purposes</p>' if demo else ""
    return rf"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{client_name} — ReachNG Portal</title>
<style>
  :root {{
    --bg: #0a0a0a; --card: #111; --border: #222;
    --orange: #ff5c00; --green: #00e5a0; --gold: #f5c842;
    --white: #f0f0f0; --muted: #888; --dim: #444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--white); font-family: 'Courier New', monospace; padding: 32px; min-height: 100vh; }}
  h1 {{ font-size: 22px; color: var(--orange); margin-bottom: 4px; }}
  .sub {{ color: var(--muted); font-size: 12px; letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 32px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); padding: 16px; border-radius: 4px; }}
  .card .val {{ font-size: 28px; font-weight: 700; }}
  .card .lbl {{ font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }}
  .orange {{ color: var(--orange); }} .green {{ color: var(--green); }} .gold {{ color: var(--gold); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: var(--muted); border-bottom: 1px solid var(--border); padding: 8px 6px; font-weight: normal; text-transform: uppercase; letter-spacing: 0.1em; font-size: 10px; }}
  td {{ padding: 8px 6px; border-bottom: 1px solid #1a1a1a; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; }}
  .badge-new {{ background: #1a2a1a; color: var(--green); }}
  .badge-contacted {{ background: #2a1a00; color: var(--orange); }}
  .badge-replied {{ background: #1a1a2a; color: #88f; }}
  .badge-converted {{ background: #002a1a; color: var(--green); }}
  .badge-opted_out {{ background: #2a1a1a; color: #f44; }}
  .roi-bar {{ background: var(--card); border: 1px solid var(--border); padding: 20px; border-radius: 4px; margin-bottom: 32px; }}
  .roi-label {{ font-size: 14px; color: var(--green); margin-top: 8px; }}
  #loading {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<h1>{client_name}</h1>
<p class="sub">{vertical} &nbsp;·&nbsp; Powered by ReachNG &nbsp;·&nbsp; Last 30 days</p>

{demo_banner}
<div id="loading">Loading your dashboard…</div>
<div id="content" style="display:none;">
  <div class="grid" id="stats-grid"></div>
  <div class="roi-bar" id="roi-bar"></div>
  <h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:0.15em;margin-bottom:12px;">Your Leads</h2>
  <table>
    <thead>
      <tr>
        <th>Business</th><th>Category</th><th>Phone</th><th>Rating</th><th>Score</th><th>Status</th>
      </tr>
    </thead>
    <tbody id="contacts-tbody"></tbody>
  </table>
</div>

<script>
const DEMO_DATA = {{
  stats: {{ contacted: 47, replied: 12, converted: 3, daily_sent: 18 }},
  roi: {{ messages_sent: 47, value_generated_ngn: 450000, roi_percent: "9.0", roi_label: "Strong pipeline — 3 deals in progress" }},
  contacts: [
    {{ name: "Landmark Africa Properties", category: "Real Estate", phone: "+2348012345678", rating: 4.7, lead_score: 91, status: "replied" }},
    {{ name: "Ocean Bay Developers", category: "Property Developer", phone: "+2348023456789", rating: 4.5, lead_score: 86, status: "contacted" }},
    {{ name: "Lekki Phase 1 Realty", category: "Real Estate", phone: "+2348034567890", rating: 4.3, lead_score: 82, status: "converted" }},
    {{ name: "VI Premium Homes", category: "Real Estate", phone: "+2348045678901", rating: 4.1, lead_score: 78, status: "contacted" }},
    {{ name: "Ikoyi Luxury Estates", category: "Property Developer", phone: "+2348056789012", rating: 4.8, lead_score: 94, status: "replied" }},
    {{ name: "Ajah New Town Developers", category: "Real Estate", phone: "+2348067890123", rating: 3.9, lead_score: 71, status: "new" }},
    {{ name: "Greenfield Homes Lagos", category: "Real Estate", phone: "+2348078901234", rating: 4.2, lead_score: 79, status: "contacted" }},
    {{ name: "Prime Properties NG", category: "Property Developer", phone: "+2348089012345", rating: 4.6, lead_score: 88, status: "converted" }},
  ]
}};

async function load() {{
  {data_loader}
  document.getElementById('loading').style.display = 'none';
  document.getElementById('content').style.display = '';

  // Stats
  const s = data.stats;
  const statsGrid = document.getElementById('stats-grid');
  const statItems = [
    {{ val: s.contacted || 0, lbl: 'Contacted', cls: 'orange' }},
    {{ val: s.replied || 0,   lbl: 'Replied',   cls: 'green' }},
    {{ val: s.converted || 0, lbl: 'Converted', cls: 'gold' }},
    {{ val: s.daily_sent || 0, lbl: 'Sent Today', cls: 'white' }},
  ];
  statsGrid.innerHTML = statItems.map(i =>
    `<div class="card"><div class="val ${{i.cls}}">${{i.val}}</div><div class="lbl">${{i.lbl}}</div></div>`
  ).join('');

  // ROI
  const roi = data.roi;
  document.getElementById('roi-bar').innerHTML = `
    <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">ROI Summary · Last 30 Days</div>
    <div class="roi-label">${{roi.roi_label || 'No activity yet'}}</div>
    <div style="display:flex;gap:32px;margin-top:12px;">
      <div><div style="font-size:18px;color:var(--orange);">${{roi.messages_sent}}</div><div style="font-size:10px;color:var(--muted);">Messages Sent</div></div>
      <div><div style="font-size:18px;color:var(--green);">₦${{(roi.value_generated_ngn||0).toLocaleString()}}</div><div style="font-size:10px;color:var(--muted);">Value Generated</div></div>
      <div><div style="font-size:18px;color:var(--gold);">${{roi.roi_percent}}x</div><div style="font-size:10px;color:var(--muted);">ROI</div></div>
    </div>
  `;

  // Contacts table
  const tbody = document.getElementById('contacts-tbody');
  tbody.innerHTML = data.contacts.map(c => `
    <tr>
      <td>${{c.name}}</td>
      <td style="color:var(--muted)">${{c.category || '—'}}</td>
      <td style="color:var(--muted)">${{c.phone || '—'}}</td>
      <td>${{c.rating ? '★ ' + c.rating : '—'}}</td>
      <td><span style="color:var(--orange)">${{c.lead_score ?? '—'}}</span></td>
      <td><span class="badge badge-${{c.status}}">${{c.status}}</span></td>
    </tr>
  `).join('');
}}
load();
</script>
</body>
</html>"""
