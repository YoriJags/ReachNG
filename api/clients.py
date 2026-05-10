"""
Client management — each paying ReachNG client gets their own campaign brief.
The brief replaces the generic vertical prompt, making every message on-brand for them.
"""
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from database import get_db

router = APIRouter(prefix="/clients", tags=["Clients"])

PaymentStatus = Literal["trial", "active", "overdue", "churned"]
PlanTier = Literal["starter", "growth", "agency"]

def _get_plan_limit(plan_key: str) -> int:
    """Fetch message limit from DB plans collection. Falls back to hardcoded defaults."""
    try:
        from api.plans import get_plan_limit
        return get_plan_limit(plan_key)
    except Exception:
        return {"starter": 200, "growth": 500, "agency": 9999}.get(plan_key, 200)


def get_clients():
    return get_db()["clients"]


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    for f in ("created_at", "updated_at", "onboarded_at", "paid_until"):
        if hasattr(doc.get(f), "isoformat"):
            doc[f] = doc[f].isoformat()
    return doc


def get_monthly_message_count(client_name: str) -> int:
    """Count messages sent for this client in the current calendar month."""
    from database import get_outreach_log, get_contacts
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Find contact IDs for this client
    contact_ids = [
        doc["_id"] for doc in get_contacts().find(
            {"client_name": client_name}, {"_id": 1}
        )
    ]
    if not contact_ids:
        return 0
    return get_outreach_log().count_documents({
        "contact_id": {"$in": contact_ids},
        "sent_at": {"$gte": month_start},
    })


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ClientUpsert(BaseModel):
    name: str
    vertical: str
    brief: str
    preferred_channel: str = "whatsapp"
    active: bool = True
    plan: PlanTier = "starter"
    payment_status: PaymentStatus = "trial"
    monthly_fee_ngn: Optional[int] = None       # What they pay per month
    paid_until: Optional[datetime] = None        # Next renewal date
    onboarded_at: Optional[datetime] = None
    cities: list[str] = []
    city: Optional[str] = None
    whatsapp_provider: str = "unipile"
    whatsapp_account_id: Optional[str] = None
    email_account_id: Optional[str] = None
    meta_phone_number_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    daily_send_limit: Optional[int] = None   # Overrides global DAILY_SEND_LIMIT for this client
    product: Optional[str] = "reachng"       # "reachng" | "digital_associates" | "loan_officer"
    autopilot: bool = False                  # If True, safe drafts send without human approval
    owner_phone: Optional[str] = None       # Client's WhatsApp number — receives morning brief
    signal_listening: bool = False          # Opt-in: monitor social for buyer intent signals
    signal_queries: list[str] = []          # Client-specific DDG queries for signal listener
    holding_message: str = ""               # Auto-fired instantly to inbound while real draft is being prepared (empty = disabled)


class PaymentUpdate(BaseModel):
    payment_status: PaymentStatus
    paid_until: Optional[datetime] = None
    monthly_fee_ngn: Optional[int] = None
    plan: Optional[PlanTier] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_clients():
    clients = list(get_clients().find({}).sort("created_at", -1))
    return [_serialise(c) for c in clients]


@router.get("/summary")
async def clients_summary():
    """Aggregate counts for Control Tower revenue panel."""
    clients = list(get_clients().find({"active": True}, {
        "name": 1, "plan": 1, "payment_status": 1,
        "monthly_fee_ngn": 1, "paid_until": 1,
    }))
    now = datetime.now(timezone.utc)
    total_mrr = 0
    by_status: dict[str, int] = {"trial": 0, "active": 0, "overdue": 0, "churned": 0}
    overdue_clients = []

    for c in clients:
        status = c.get("payment_status", "trial")
        by_status[status] = by_status.get(status, 0) + 1
        fee = c.get("monthly_fee_ngn") or 0
        if status == "active":
            total_mrr += fee
        # Auto-detect overdue: paid_until in the past but still marked active
        paid_until = c.get("paid_until")
        if paid_until and paid_until < now and status == "active":
            overdue_clients.append(c.get("name"))

    return {
        "total_active": by_status["active"],
        "total_trial": by_status["trial"],
        "total_overdue": by_status["overdue"],
        "total_churned": by_status["churned"],
        "mrr_ngn": total_mrr,
        "overdue_clients": overdue_clients,
    }


@router.get("/{name}/stats")
async def client_stats(name: str):
    """Full stats for one client — used by Control Tower drill-down."""
    client = get_clients().find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")

    from database import get_contacts
    contacts_col = get_contacts()
    total_leads    = contacts_col.count_documents({"client_name": name})
    contacted      = contacts_col.count_documents({"client_name": name, "status": "contacted"})
    replied        = contacts_col.count_documents({"client_name": name, "status": "replied"})
    converted      = contacts_col.count_documents({"client_name": name, "status": "converted"})
    closed         = contacts_col.count_documents({"client_name": name, "closed_by_client": True})
    messages_month = get_monthly_message_count(name)
    plan           = client.get("plan", "starter")
    limit          = _get_plan_limit(plan)

    return {
        "client": name,
        "plan": plan,
        "payment_status": client.get("payment_status", "trial"),
        "monthly_fee_ngn": client.get("monthly_fee_ngn"),
        "paid_until": client.get("paid_until", "").isoformat() if client.get("paid_until") else None,
        "messages_this_month": messages_month,
        "monthly_limit": limit,
        "usage_pct": round(messages_month / limit * 100, 1) if limit < 9999 else 0,
        "leads": {
            "total": total_leads,
            "contacted": contacted,
            "replied": replied,
            "converted": converted,
            "closed_won": closed,
        },
    }


@router.get("/{name}")
async def get_client(name: str):
    client = get_clients().find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")
    return _serialise(client)


SUPPORTED_VERTICALS = {
    "real_estate", "education", "professional_services", "hospitality",
    "clinics", "small_business", "fitness", "events", "auto", "cooperatives",
    "legal", "insurance", "recruitment", "general",
}


@router.post("/")
async def upsert_client(payload: ClientUpsert):
    """Create or update a client. Vertical is required and must be a known tag —
    drives Business Brief primer + Closer persona + downstream routing.
    """
    if not payload.vertical or not payload.vertical.strip():
        raise HTTPException(400, "vertical is required — every client must be tagged so the right persona/primer fires")
    vertical = payload.vertical.strip().lower()
    if vertical not in SUPPORTED_VERTICALS:
        raise HTTPException(400, f"vertical '{payload.vertical}' not recognised. Use one of: {sorted(SUPPORTED_VERTICALS)}")
    payload.vertical = vertical

    now = datetime.now(timezone.utc)
    clients = get_clients()

    set_doc = {
        "name":                  payload.name,
        "vertical":              payload.vertical,
        "brief":                 payload.brief,
        "preferred_channel":     payload.preferred_channel,
        "active":                payload.active,
        "plan":                  payload.plan,
        "payment_status":        payload.payment_status,
        "city":                  payload.city,
        "cities":                payload.cities,
        "whatsapp_provider":     payload.whatsapp_provider,
        "whatsapp_account_id":   payload.whatsapp_account_id,
        "email_account_id":      payload.email_account_id,
        "meta_phone_number_id":  payload.meta_phone_number_id,
        "meta_access_token":     payload.meta_access_token,
        "updated_at":            now,
    }
    if payload.monthly_fee_ngn is not None:
        set_doc["monthly_fee_ngn"] = payload.monthly_fee_ngn
    if payload.paid_until:
        set_doc["paid_until"] = payload.paid_until
    if payload.onboarded_at:
        set_doc["onboarded_at"] = payload.onboarded_at
    if payload.daily_send_limit is not None:
        set_doc["daily_send_limit"] = payload.daily_send_limit
    if payload.product is not None:
        set_doc["product"] = payload.product
    set_doc["autopilot"] = payload.autopilot
    if payload.owner_phone is not None:
        set_doc["owner_phone"] = payload.owner_phone
    set_doc["signal_listening"] = payload.signal_listening
    if payload.signal_queries:
        set_doc["signal_queries"] = payload.signal_queries
    set_doc["holding_message"] = payload.holding_message

    result = clients.update_one(
        {"name": {"$regex": f"^{re.escape(payload.name)}$", "$options": "i"}},
        {
            "$set": set_doc,
            "$setOnInsert": {
                "created_at": now,
                "onboarded_at": payload.onboarded_at or now,
            },
        },
        upsert=True,
    )

    action = "created" if result.upserted_id else "updated"
    return {"success": True, "action": action, "client": payload.name}


@router.patch("/{name}/payment")
async def update_payment_status(name: str, payload: PaymentUpdate):
    """Update billing status — mark as paid, overdue, churned etc."""
    clients = get_clients()
    update: dict = {
        "payment_status": payload.payment_status,
        "updated_at": datetime.now(timezone.utc),
    }
    if payload.paid_until:
        update["paid_until"] = payload.paid_until
    if payload.monthly_fee_ngn is not None:
        update["monthly_fee_ngn"] = payload.monthly_fee_ngn
    if payload.plan:
        update["plan"] = payload.plan

    result = clients.update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "payment_status": payload.payment_status}


@router.get("/{name}/invoice", response_class=HTMLResponse)
async def generate_invoice(
    name: str,
    request: Request,
    month: Optional[str] = None,    # e.g. "2026-04" — defaults to current month
    include_vat: bool = False,
):
    """
    Render a printable HTML invoice for a client.
    month format: YYYY-MM (default: current month)
    """
    client = get_clients().find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not client:
        raise HTTPException(404, f"Client '{name}' not found")

    now = datetime.now(timezone.utc)

    # Parse billing month
    if month:
        try:
            period_dt = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "month must be YYYY-MM format")
    else:
        period_dt = now.replace(day=1)

    billing_period = period_dt.strftime("%B %Y")
    issued_date    = now.strftime("%d %B %Y")
    due_date       = (now + timedelta(days=7)).strftime("%d %B %Y")

    # Invoice number: RC-{client_initials}-{YYYYMM}-{seq}
    initials = "".join(w[0].upper() for w in client["name"].split()[:2])
    seq = _next_invoice_seq(client["name"])
    invoice_number = f"RC-{initials}-{period_dt.strftime('%Y%m')}-{seq:03d}"

    # Stats for this billing period
    messages_sent  = get_monthly_message_count(client["name"])
    plan           = client.get("plan", "starter")
    monthly_fee    = client.get("monthly_fee_ngn", 0) or 0
    plan_limit     = _get_plan_limit(plan)

    from database import get_contacts
    contacts_col = get_contacts()
    total_leads  = contacts_col.count_documents({"client_name": name})
    deals_closed = contacts_col.count_documents({"client_name": name, "closed_by_client": True})
    deal_value   = sum(
        d.get("deal_value_ngn", 0)
        for d in contacts_col.find({"client_name": name, "closed_by_client": True}, {"deal_value_ngn": 1})
    )

    # Line items
    line_items = [
        {
            "description": f"{plan.title()} Plan — Monthly Outreach Service",
            "note": f"{billing_period} · {plan_limit if plan_limit < 9999 else 'Unlimited'} messages/month",
            "qty": 1,
            "unit_price": monthly_fee,
            "amount": monthly_fee,
        },
    ]

    subtotal = monthly_fee
    vat      = round(subtotal * 0.075) if include_vat else 0
    total    = subtotal + vat

    invoice_data = {
        "number":          invoice_number,
        "issued_date":     issued_date,
        "billing_period":  billing_period,
        "due_date":        due_date,
        "payment_status":  client.get("payment_status", "due"),
        "plan":            plan,
        "client_name":     client["name"],
        "client_vertical": client.get("vertical", ""),
        "client_city":     client.get("city", ""),
        "line_items":      line_items,
        "subtotal":        subtotal,
        "vat":             vat,
        "total":           total,
        "messages_sent":   messages_sent,
        "total_leads":     total_leads,
        "deals_closed":    deals_closed,
        "deal_value_ngn":  deal_value,
        # Payment details — set via env vars
        "bank_name":       _get_setting("BANK_NAME"),
        "account_name":    _get_setting("ACCOUNT_NAME"),
        "account_number":  _get_setting("ACCOUNT_NUMBER"),
    }

    # Store invoice record
    _store_invoice(client["name"], invoice_number, total, billing_period)

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "invoice.html", {"invoice": invoice_data})


def _next_invoice_seq(client_name: str) -> int:
    """Auto-increment invoice sequence per client."""
    col = get_db()["reachng_invoices"]
    count = col.count_documents({"client_name": client_name})
    return count + 1


def _store_invoice(client_name: str, number: str, total: int, period: str):
    """Persist invoice record so we can show history in the portal."""
    col = get_db()["reachng_invoices"]
    col.update_one(
        {"number": number},
        {"$setOnInsert": {
            "client_name": client_name,
            "number": number,
            "total_ngn": total,
            "billing_period": period,
            "created_at": datetime.now(timezone.utc),
            "paid": False,
        }},
        upsert=True,
    )


def _get_setting(key: str) -> Optional[str]:
    import os
    return os.environ.get(key)


@router.get("/{name}/invoices")
async def list_invoices(name: str):
    """List all invoices generated for a client."""
    invoices = list(
        get_db()["reachng_invoices"]
        .find({"client_name": name})
        .sort("created_at", -1)
    )
    for inv in invoices:
        inv["id"] = str(inv.pop("_id"))
        if hasattr(inv.get("created_at"), "isoformat"):
            inv["created_at"] = inv["created_at"].isoformat()
    return invoices


@router.patch("/{name}/autopilot")
async def set_autopilot(name: str, enabled: bool):
    """Toggle autopilot mode on/off for a client."""
    result = get_clients().update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": {"autopilot": enabled, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "autopilot": enabled}


@router.patch("/{name}/signal-listening")
async def set_signal_listening(name: str, enabled: bool):
    """Toggle signal listening on/off for a client."""
    result = get_clients().update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": {"signal_listening": enabled, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "signal_listening": enabled}


class HoldingMessageUpdate(BaseModel):
    holding_message: str


@router.patch("/{name}/holding-message")
async def set_holding_message(name: str, payload: HoldingMessageUpdate):
    """Update the holding reply auto-fired to inbound while real draft is prepared.
    Empty string disables the feature.
    """
    msg = (payload.holding_message or "").strip()
    if len(msg) > 800:
        raise HTTPException(400, "Holding message too long — keep under 800 characters")
    result = get_clients().update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": {"holding_message": msg, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "holding_message": msg}


@router.delete("/{name}")
async def deactivate_client(name: str):
    """Soft-delete — marks client inactive."""
    result = get_clients().update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": {"active": False, "payment_status": "churned", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Client '{name}' not found")
    return {"success": True, "client": name, "status": "deactivated"}
