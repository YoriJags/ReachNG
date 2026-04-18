"""
EstateOS Rent Roll — unit inventory + tenant ledger + automated rent chase.

Data model:
  estate_units       — one row per rentable unit (address, rent, landlord)
  estate_tenants     — current + past tenants, linked to unit
  estate_rent_ledger — monthly rent charges (opened on due date, closed on payment)

Chase loop:
  Daily cron scans estate_rent_ledger for open charges past due date.
  For each overdue charge → generate WhatsApp draft (polite/firm/serious/final)
  → queue in HITL Message Queue. Landlord taps Send.
"""
from datetime import datetime, timezone, timedelta
from database.mongo import get_db
from bson import ObjectId
import structlog

log = structlog.get_logger()

# Chase escalation: stages by days overdue
CHASE_STAGES = [
    {"min_days": 1,  "stage": "reminder", "tone": "friendly",  "label": "Gentle Reminder"},
    {"min_days": 7,  "stage": "follow_up","tone": "firm",      "label": "Firm Follow-Up"},
    {"min_days": 14, "stage": "serious",  "tone": "serious",   "label": "Serious Notice"},
    {"min_days": 30, "stage": "warning",  "tone": "warning",   "label": "Quit Notice Warning"},
    {"min_days": 60, "stage": "final",    "tone": "final",     "label": "Formal Quit Notice"},
]


def _col(name: str):
    return get_db()[name]


def ensure_rent_indexes():
    _col("estate_units").create_index([("landlord_company", 1), ("address", 1)])
    _col("estate_tenants").create_index([("unit_id", 1), ("status", 1)])
    _col("estate_rent_ledger").create_index([("unit_id", 1), ("period", 1)], unique=True)
    _col("estate_rent_ledger").create_index([("status", 1), ("due_date", 1)])


def stage_for_days_overdue(days: int) -> dict:
    applicable = [s for s in CHASE_STAGES if s["min_days"] <= days]
    return applicable[-1] if applicable else CHASE_STAGES[0]


# ── Units ─────────────────────────────────────────────────────────────────────

def add_unit(landlord_company: str, address: str, unit_label: str,
             monthly_rent_ngn: float, rent_cycle: str = "monthly",
             property_type: str = "residential",
             landlord_bank_name: str = "", landlord_account_number: str = "",
             landlord_account_name: str = "", landlord_phone: str = "") -> str:
    doc = {
        "landlord_company":        landlord_company,
        "address":                 address,
        "unit_label":              unit_label,
        "monthly_rent_ngn":        monthly_rent_ngn,
        "rent_cycle":              rent_cycle,  # monthly | quarterly | annual
        "property_type":           property_type,
        "landlord_bank_name":      landlord_bank_name,
        "landlord_account_number": landlord_account_number,
        "landlord_account_name":   landlord_account_name,
        "landlord_phone":          landlord_phone,
        "status":                  "active",
        "created_at":              datetime.now(timezone.utc),
    }
    result = _col("estate_units").insert_one(doc)
    return str(result.inserted_id)


def list_units(landlord_company: str = "") -> list[dict]:
    q = {"landlord_company": landlord_company} if landlord_company else {}
    rows = list(_col("estate_units").find(q).sort("address", 1))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


# ── Tenants ───────────────────────────────────────────────────────────────────

def assign_tenant(unit_id: str, tenant_name: str, tenant_phone: str,
                  tenant_email: str, lease_start: str, lease_months: int = 12,
                  rent_due_day: int = 1) -> str:
    doc = {
        "unit_id":       unit_id,
        "tenant_name":   tenant_name,
        "tenant_phone":  tenant_phone,
        "tenant_email":  tenant_email,
        "lease_start":   lease_start,
        "lease_months":  lease_months,
        "rent_due_day":  rent_due_day,
        "status":        "active",
        "created_at":    datetime.now(timezone.utc),
    }
    result = _col("estate_tenants").insert_one(doc)
    return str(result.inserted_id)


def list_tenants(unit_id: str = "") -> list[dict]:
    q = {"status": "active"}
    if unit_id:
        q["unit_id"] = unit_id
    rows = list(_col("estate_tenants").find(q).sort("tenant_name", 1))
    for r in rows:
        r["_id"] = str(r["_id"])
    return rows


# ── Rent Ledger ───────────────────────────────────────────────────────────────

def open_charge(unit_id: str, tenant_id: str, period: str, amount_ngn: float,
                due_date: datetime) -> str:
    """Open a monthly rent charge. period='YYYY-MM'."""
    doc = {
        "unit_id":   unit_id,
        "tenant_id": tenant_id,
        "period":    period,
        "amount_ngn": amount_ngn,
        "due_date":  due_date,
        "status":    "open",
        "paid_at":   None,
        "paid_amount": 0.0,
        "last_chased_at": None,
        "chase_count":    0,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = _col("estate_rent_ledger").insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        log.warning("rent_charge_duplicate", unit_id=unit_id, period=period, error=str(e))
        return ""


def mark_paid(charge_id: str, amount_paid: float | None = None):
    update = {
        "status":      "paid",
        "paid_at":     datetime.now(timezone.utc),
    }
    if amount_paid is not None:
        update["paid_amount"] = amount_paid
    _col("estate_rent_ledger").update_one(
        {"_id": ObjectId(charge_id)},
        {"$set": update},
    )


def get_overdue_charges(landlord_company: str = "") -> list[dict]:
    """Return open charges whose due_date has passed. Join with unit + tenant."""
    now = datetime.now(timezone.utc)
    match = {"status": "open", "due_date": {"$lt": now}}
    charges = list(_col("estate_rent_ledger").find(match).sort("due_date", 1))

    enriched = []
    for c in charges:
        unit = _col("estate_units").find_one({"_id": ObjectId(c["unit_id"])})
        if not unit:
            continue
        if landlord_company and unit.get("landlord_company") != landlord_company:
            continue
        tenant = _col("estate_tenants").find_one({"_id": ObjectId(c["tenant_id"])})
        if not tenant:
            continue

        days_overdue = (now - c["due_date"]).days
        stage = stage_for_days_overdue(days_overdue)

        c["_id"] = str(c["_id"])
        c["unit"]   = {"address": unit["address"], "unit_label": unit.get("unit_label", ""),
                       "landlord_company":        unit.get("landlord_company", ""),
                       "landlord_bank_name":      unit.get("landlord_bank_name", ""),
                       "landlord_account_number": unit.get("landlord_account_number", ""),
                       "landlord_account_name":   unit.get("landlord_account_name", ""),
                       "landlord_phone":          unit.get("landlord_phone", "")}
        c["tenant"] = {"name": tenant["tenant_name"], "phone": tenant.get("tenant_phone", ""),
                       "email": tenant.get("tenant_email", "")}
        c["days_overdue"] = days_overdue
        c["stage"] = stage
        enriched.append(c)
    return enriched


def record_chase(charge_id: str):
    _col("estate_rent_ledger").update_one(
        {"_id": ObjectId(charge_id)},
        {"$set": {"last_chased_at": datetime.now(timezone.utc)},
         "$inc": {"chase_count": 1}},
    )


# ── Roll-open helper ──────────────────────────────────────────────────────────

def open_charges_for_period(period: str) -> int:
    """
    Idempotently open a rent charge for every active tenant for `period` (YYYY-MM).
    Due date = rent_due_day of that month. Amount = unit.monthly_rent_ngn.
    Safe to run repeatedly — unique index blocks duplicates.
    """
    year, month = [int(x) for x in period.split("-")]
    tenants = list(_col("estate_tenants").find({"status": "active"}))
    opened = 0
    for t in tenants:
        unit = _col("estate_units").find_one({"_id": ObjectId(t["unit_id"])})
        if not unit:
            continue
        due_day = int(t.get("rent_due_day", 1))
        try:
            due = datetime(year, month, due_day, tzinfo=timezone.utc)
        except ValueError:
            due = datetime(year, month, 28, tzinfo=timezone.utc)
        cid = open_charge(str(unit["_id"]), str(t["_id"]), period,
                          float(unit["monthly_rent_ngn"]), due)
        if cid:
            opened += 1
    log.info("rent_period_opened", period=period, opened=opened)
    return opened
