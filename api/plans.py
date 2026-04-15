"""
Plan tier management — Starter / Growth / Agency (or whatever you name them).
All plan configs live in MongoDB `reachng_plans` collection so they can be
edited from the Control Tower without touching code.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from database import get_db

router = APIRouter(prefix="/plans", tags=["Plans"])

# ── Default seed data ─────────────────────────────────────────────────────────
DEFAULT_PLANS = [
    # ── ReachNG (outreach) plans ──────────────────────────────────────────────
    {
        "key":               "starter",
        "name":              "Starter",
        "product":           "reachng",
        "message_limit":     200,
        "default_fee_ngn":   50000,
        "description":       "Great for small businesses just getting started with outreach.",
        "color":             "#555555",
        "active":            True,
    },
    {
        "key":               "growth",
        "name":              "Growth",
        "product":           "reachng",
        "message_limit":     500,
        "default_fee_ngn":   120000,
        "description":       "For businesses scaling their pipeline aggressively.",
        "color":             "#f5c842",
        "active":            True,
    },
    {
        "key":               "agency",
        "name":              "Agency",
        "product":           "reachng",
        "message_limit":     9999,
        "default_fee_ngn":   250000,
        "description":       "Unlimited outreach for high-volume operators.",
        "color":             "#ff5500",
        "active":            True,
    },
    # ── Digital Associates (AI contract review) — single product plan ───────────
    {
        "key":               "digital_associates",
        "name":              "Digital Associates",
        "product":           "digital_associates",
        "message_limit":     9999,
        "default_fee_ngn":   150000,
        "description":       "AI contract review for Nigerian law firms. Unlimited reviews, CBN/CAMA/NDPR grounded.",
        "color":             "#6366f1",
        "active":            True,
    },
    # ── AI Loan Officer plans ─────────────────────────────────────────────────
    {
        "key":               "loan_branch",
        "name":              "Branch Plan",
        "product":           "loan_officer",
        "message_limit":     9999,
        "default_fee_ngn":   150000,
        "description":       "Up to 100 scored applications/month per branch. Ideal for single-branch MFBs.",
        "color":             "#16a34a",
        "active":            True,
    },
    {
        "key":               "loan_enterprise",
        "name":              "Enterprise Plan",
        "product":           "loan_officer",
        "message_limit":     9999,
        "default_fee_ngn":   350000,
        "description":       "Unlimited applications. Multi-branch dashboard. Dedicated support.",
        "color":             "#15803d",
        "active":            True,
    },
]


def get_plans_col():
    return get_db()["reachng_plans"]


def seed_plans_if_empty():
    """
    Called at startup — upserts all default plans.
    $setOnInsert inserts full doc on first run; $set only touches `product` + `updated_at`
    so manual edits to name/fee/color are preserved on subsequent restarts.
    """
    col = get_plans_col()
    now = datetime.now(timezone.utc)
    for p in DEFAULT_PLANS:
        # $setOnInsert: fields that only get written on first insert
        # Excludes product + updated_at because $set also touches those (no path conflict)
        insert_only = {k: v for k, v in p.items() if k not in ("product", "updated_at")}
        insert_only["created_at"] = now
        col.update_one(
            {"key": p["key"]},
            {
                "$setOnInsert": insert_only,
                "$set": {"product": p["product"], "updated_at": now},
            },
            upsert=True,
        )
    # Backfill product field for plans that predate this field
    col.update_many(
        {"product": {"$exists": False}},
        {"$set": {"product": "reachng"}},
    )


def get_plan_limit(plan_key: str) -> int:
    """Fetch message limit for a plan key. Falls back to 200 if not found."""
    col = get_plans_col()
    doc = col.find_one({"key": plan_key}, {"message_limit": 1})
    if doc:
        return doc.get("message_limit", 200)
    # Fallback for any plan not in DB
    return 200


def get_all_plans_map() -> dict[str, dict]:
    """Returns {key: plan_doc} for all active plans."""
    col = get_plans_col()
    return {p["key"]: p for p in col.find({"active": True})}


def _serialise(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    for f in ("created_at", "updated_at"):
        if hasattr(doc.get(f), "isoformat"):
            doc[f] = doc[f].isoformat()
    return doc


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlanUpsert(BaseModel):
    name:             str
    product:          Optional[str] = "reachng"   # "reachng" | "digital_associates" | "loan_officer"
    message_limit:    int = Field(ge=1)
    default_fee_ngn:  int = Field(ge=0)
    description:      Optional[str] = ""
    color:            Optional[str] = "#888888"
    active:           bool = True


class PlanUpdate(BaseModel):
    name:             Optional[str] = None
    product:          Optional[str] = None
    message_limit:    Optional[int] = Field(default=None, ge=1)
    default_fee_ngn:  Optional[int] = Field(default=None, ge=0)
    description:      Optional[str] = None
    color:            Optional[str] = None
    active:           Optional[bool] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def list_plans():
    plans = list(get_plans_col().find({}).sort("default_fee_ngn", 1))
    return [_serialise(p) for p in plans]


@router.post("/")
async def create_plan(key: str, payload: PlanUpsert):
    """
    Create a new plan tier. `key` must be a unique slug (e.g. 'enterprise').
    Existing plans (starter/growth/agency) can be updated via PATCH instead.
    """
    col = get_plans_col()
    if col.find_one({"key": key}):
        raise HTTPException(400, f"Plan '{key}' already exists. Use PATCH to update it.")
    now = datetime.now(timezone.utc)
    doc = {
        "key": key,
        "name": payload.name,
        "product": payload.product or "reachng",
        "message_limit": payload.message_limit,
        "default_fee_ngn": payload.default_fee_ngn,
        "description": payload.description,
        "color": payload.color,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
    }
    col.insert_one(doc)
    return {"success": True, "key": key}


@router.patch("/{key}")
async def update_plan(key: str, payload: PlanUpdate):
    """Edit any field on a plan — name, limits, fee, description, color, active."""
    col = get_plans_col()
    update = {"updated_at": datetime.now(timezone.utc)}
    if payload.name is not None:
        update["name"] = payload.name
    if payload.message_limit is not None:
        update["message_limit"] = payload.message_limit
    if payload.default_fee_ngn is not None:
        update["default_fee_ngn"] = payload.default_fee_ngn
    if payload.description is not None:
        update["description"] = payload.description
    if payload.color is not None:
        update["color"] = payload.color
    if payload.active is not None:
        update["active"] = payload.active
    if payload.product is not None:
        update["product"] = payload.product

    result = col.update_one({"key": key}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, f"Plan '{key}' not found")
    return {"success": True, "key": key}


@router.get("/product-mrr")
async def product_mrr():
    """
    Returns MRR broken down by product line.
    Sums monthly_fee_ngn for active clients, grouped by their `product` field.
    """
    from database import get_db
    clients_col = get_db()["clients"]
    pipeline = [
        {"$match": {"payment_status": "active", "active": True}},
        {"$group": {
            "_id": "$product",
            "mrr": {"$sum": {"$ifNull": ["$monthly_fee_ngn", 0]}},
            "count": {"$sum": 1},
        }},
    ]
    rows = list(clients_col.aggregate(pipeline))
    result = {}
    total = 0
    for r in rows:
        product = r["_id"] or "reachng"
        result[product] = {"mrr_ngn": r["mrr"], "clients": r["count"]}
        total += r["mrr"]
    result["total_mrr_ngn"] = total
    return result


@router.delete("/{key}")
async def delete_plan(key: str):
    """Soft-delete a plan (marks inactive). Cannot delete the 3 default plans."""
    if key in ("starter", "growth", "agency"):
        raise HTTPException(400, "Cannot delete default plans. Deactivate them instead.")
    result = get_plans_col().update_one(
        {"key": key},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, f"Plan '{key}' not found")
    return {"success": True, "key": key, "status": "deactivated"}
