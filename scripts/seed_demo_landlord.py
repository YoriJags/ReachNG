"""
Seed a demo Lagos landlord with realistic rent-roll data for pitch/sales calls.

Usage:
    python -m scripts.seed_demo_landlord            # seed (idempotent)
    python -m scripts.seed_demo_landlord --wipe     # delete then reseed
    python -m scripts.seed_demo_landlord --token    # just print the portal link

What it creates:
    - client 'Demo Landlord NG' (vertical=real_estate, active, portal token)
    - 5 units across Lekki / VI / Ikeja with bank details on the landlord
    - 4 active tenants
    - current-month ledger: 1 paid, 3 overdue at chase stages
      (reminder / follow_up / warning) so the portal shows the full loop
    - 1 historic paid charge (previous month) so Collected This Month > 0
"""
from __future__ import annotations
import argparse
import secrets
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from database.mongo import get_db
from services.estate.rent_roll import ensure_rent_indexes


DEMO_NAME = "ReachNG Demo"
LANDLORD_PHONE = "+2348000000001"

UNITS = [
    {"address": "14B Admiralty Way, Lekki Phase 1, Lagos", "unit_label": "Flat 2",
     "monthly_rent_ngn": 450_000, "property_type": "residential"},
    {"address": "22 Adeola Odeku, Victoria Island, Lagos", "unit_label": "Suite 3A",
     "monthly_rent_ngn": 850_000, "property_type": "commercial"},
    {"address": "7 Bode Thomas, Surulere, Lagos", "unit_label": "",
     "monthly_rent_ngn": 250_000, "property_type": "residential"},
    {"address": "31 Allen Avenue, Ikeja, Lagos", "unit_label": "Shop 5",
     "monthly_rent_ngn": 320_000, "property_type": "commercial"},
    {"address": "9 Chief Yesufu Abiodun, Oniru, Lagos", "unit_label": "Block B",
     "monthly_rent_ngn": 600_000, "property_type": "residential"},
]

TENANTS = [
    {"name": "Adaeze Okafor",   "phone": "+2348011111111", "unit_idx": 0, "due_day": 1},
    {"name": "Chinedu Obi",     "phone": "+2348022222222", "unit_idx": 1, "due_day": 1},
    {"name": "Bukola Adeyemi",  "phone": "+2348033333333", "unit_idx": 2, "due_day": 5},
    {"name": "Tunde Lawal",     "phone": "+2348044444444", "unit_idx": 3, "due_day": 1},
]


def _months_ago_period(months_back: int) -> str:
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def wipe():
    db = get_db()
    unit_ids = [str(u["_id"]) for u in db["estate_units"].find({"landlord_company": DEMO_NAME})]
    db["estate_rent_ledger"].delete_many({"unit_id": {"$in": unit_ids}})
    db["estate_tenants"].delete_many({"unit_id": {"$in": unit_ids}})
    db["estate_units"].delete_many({"landlord_company": DEMO_NAME})
    db["clients"].delete_one({"name": DEMO_NAME})
    print(f"wiped: client={DEMO_NAME}, units={len(unit_ids)}")


def seed() -> str:
    ensure_rent_indexes()
    db = get_db()
    clients = db["clients"]

    now = datetime.now(timezone.utc)
    existing = clients.find_one({"name": DEMO_NAME})
    token = (existing or {}).get("portal_token") or secrets.token_urlsafe(24)

    clients.update_one(
        {"name": DEMO_NAME},
        {
            "$set": {
                "name":            DEMO_NAME,
                "vertical":        "real_estate",
                "company":         DEMO_NAME,
                "brief":           "Lagos landlord — 5 units across Lekki, VI, Surulere, Ikeja",
                "preferred_channel": "whatsapp",
                "active":          True,
                "plan":            "growth",
                "payment_status":  "trial",
                "monthly_fee_ngn": 50_000,
                "city":            "Lagos",
                "cities":          ["Lagos"],
                "portal_token":    token,
                "portal_created_at": existing.get("portal_created_at") if existing else now,
                "updated_at":      now,
            },
            "$setOnInsert": {"created_at": now, "onboarded_at": now},
        },
        upsert=True,
    )

    unit_ids: list[str] = []
    for u in UNITS:
        doc = {
            "landlord_company":        DEMO_NAME,
            "address":                 u["address"],
            "unit_label":              u["unit_label"],
            "monthly_rent_ngn":        u["monthly_rent_ngn"],
            "rent_cycle":              "monthly",
            "property_type":           u["property_type"],
            "landlord_bank_name":      "Providus Bank",
            "landlord_account_number": "6508125346",
            "landlord_account_name":   "Demo Landlord NG",
            "landlord_phone":          LANDLORD_PHONE,
            "status":                  "active",
            "created_at":              now,
        }
        existing_u = db["estate_units"].find_one(
            {"landlord_company": DEMO_NAME, "address": u["address"], "unit_label": u["unit_label"]}
        )
        if existing_u:
            unit_ids.append(str(existing_u["_id"]))
        else:
            r = db["estate_units"].insert_one(doc)
            unit_ids.append(str(r.inserted_id))

    tenant_ids: list[str] = []
    for t in TENANTS:
        unit_id = unit_ids[t["unit_idx"]]
        existing_t = db["estate_tenants"].find_one({"unit_id": unit_id, "tenant_name": t["name"]})
        if existing_t:
            tenant_ids.append(str(existing_t["_id"]))
            continue
        r = db["estate_tenants"].insert_one({
            "unit_id":       unit_id,
            "tenant_name":   t["name"],
            "tenant_phone":  t["phone"],
            "tenant_email":  "",
            "lease_start":   "2025-01-01",
            "lease_months":  12,
            "rent_due_day":  t["due_day"],
            "status":        "active",
            "created_at":    now,
        })
        tenant_ids.append(str(r.inserted_id))

    ledger = db["estate_rent_ledger"]
    ledger.delete_many({"unit_id": {"$in": unit_ids}})

    cur_period  = _months_ago_period(0)
    prev_period = _months_ago_period(1)

    plan = [
        # (tenant_idx, period, days_ago_due, paid)
        (0, prev_period, 32, True),                       # last month, paid — counts toward outstanding history
        (0, cur_period,  0,  True),                       # this month, paid — Collected This Month
        (1, cur_period,  5,  False),                      # 5 days overdue → reminder (friendly)
        (2, cur_period,  15, False),                      # 15 days overdue → serious
        (3, cur_period,  45, False),                      # 45 days overdue → warning
    ]
    for (ti, period, days_ago, paid) in plan:
        unit = next(u for u in db["estate_units"].find({"_id": ObjectId(unit_ids[TENANTS[ti]["unit_idx"]])}))
        due = now - timedelta(days=days_ago)
        doc = {
            "unit_id":    unit_ids[TENANTS[ti]["unit_idx"]],
            "tenant_id":  tenant_ids[ti],
            "period":     period,
            "amount_ngn": float(unit["monthly_rent_ngn"]),
            "due_date":   due,
            "status":     "paid" if paid else "open",
            "paid_at":    (due + timedelta(days=1)) if paid else None,
            "paid_amount": float(unit["monthly_rent_ngn"]) if paid else 0.0,
            "last_chased_at": None,
            "chase_count":    0,
            "created_at": now,
        }
        try:
            ledger.insert_one(doc)
        except Exception as e:
            print(f"ledger insert warning ({period}, {TENANTS[ti]['name']}): {e}")

    print(f"seeded: client={DEMO_NAME}")
    print(f"  units={len(unit_ids)} tenants={len(tenant_ids)} ledger entries={len(plan)}")
    print(f"  portal path=/portal/{token}")
    print(f"  also reachable at /portal/estate/{token}")
    return token


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wipe", action="store_true", help="delete demo data then reseed")
    ap.add_argument("--token", action="store_true", help="print the existing portal token then exit")
    args = ap.parse_args()

    if args.token:
        db = get_db()
        c = db["clients"].find_one({"name": DEMO_NAME})
        if not c or not c.get("portal_token"):
            print("not seeded yet — run without --token first")
            return
        print(c["portal_token"])
        return

    if args.wipe:
        wipe()
    seed()


if __name__ == "__main__":
    main()
