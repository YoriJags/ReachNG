"""
Seed a demo Lagos company with realistic TalentOS data for pitch/sales calls.

Usage:
    python -m scripts.seed_demo_talent            # seed (idempotent)
    python -m scripts.seed_demo_talent --wipe     # delete then reseed

What it creates:
    - client 'Demo Company NG' (vertical=hr, active, portal token — reuses
      existing portal_token if already seeded by seed_demo_landlord)
    - 6 staff across departments (screenings, attendance, leave, PENCOM, probation)
    - 3 pending leave requests (1 approved, 1 pending, 1 rejected)
    - Attendance log today for each staff member (mix of present / absent)
    - PENCOM records with current + 1 month arrear
    - 2 probation staff (one expiring in 7 days, one fresh)
    - 1 offboarding record
    - 1 uploaded policy doc
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone, timedelta
from database.mongo import get_db

DEMO_NAME = "ReachNG Demo"
DEMO_ESTATE_NAME = "ReachNG Demo"  # same client — one portal_token, both portals

STAFF = [
    {"name": "Emeka Nwosu",     "role": "Software Engineer",    "dept": "Engineering",  "salary": 450_000},
    {"name": "Chisom Eze",      "role": "HR Manager",           "dept": "HR",           "salary": 380_000},
    {"name": "Bayo Adeleke",    "role": "Sales Executive",      "dept": "Sales",        "salary": 300_000},
    {"name": "Fatima Usman",    "role": "Finance Analyst",      "dept": "Finance",      "salary": 420_000},
    {"name": "Seun Oladipo",    "role": "Product Manager",      "dept": "Product",      "salary": 500_000},
    {"name": "Amara Obi",       "role": "Junior Developer",     "dept": "Engineering",  "salary": 250_000},
]


def wipe():
    db = get_db()
    staff_names = [s["name"] for s in STAFF]
    db["hr_attendance_staff"].delete_many({"company": DEMO_NAME})
    db["hr_attendance_log"].delete_many({"company": DEMO_NAME})
    db["hr_leave_requests"].delete_many({"company": DEMO_NAME})
    db["hr_pencom_staff"].delete_many({"company": DEMO_NAME})
    db["hr_probation"].delete_many({"company": DEMO_NAME})
    db["hr_offboarding"].delete_many({"company": DEMO_NAME})
    db["hr_policies"].delete_many({"company": DEMO_NAME})
    db["hr_screenings"].delete_many({"company": DEMO_NAME})
    db["clients"].delete_one({"name": DEMO_NAME})
    print(f"wiped: {DEMO_NAME}")


def seed() -> str:
    db = get_db()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    # Ensure the shared demo client exists (created by seed_demo_landlord if run first)
    # If run standalone, create it here with a fresh token.
    existing = db["clients"].find_one({"name": DEMO_NAME})
    token = (existing or {}).get("portal_token") or secrets.token_urlsafe(24)
    if not existing:
        db["clients"].insert_one({
            "name":              DEMO_NAME,
            "vertical":          "real_estate",
            "company":           DEMO_NAME,
            "brief":             "ReachNG demo client — EstateOS + TalentOS showcase",
            "preferred_channel": "whatsapp",
            "active":            True,
            "plan":              "growth",
            "payment_status":    "trial",
            "monthly_fee_ngn":   130_000,
            "city":              "Lagos",
            "cities":            ["Lagos"],
            "portal_token":      token,
            "portal_created_at": now,
            "created_at":        now,
            "onboarded_at":      now,
            "updated_at":        now,
        })

    # ── Staff / Attendance ────────────────────────────────────────────────────
    db["hr_attendance_staff"].delete_many({"company": DEMO_NAME})
    staff_ids = []
    for s in STAFF:
        r = db["hr_attendance_staff"].insert_one({
            "company":      DEMO_NAME,
            "name":         s["name"],
            "role":         s["role"],
            "department":   s["dept"],
            "phone":        "+234800000000" + str(STAFF.index(s)),
            "active":       True,
            "created_at":   now,
        })
        staff_ids.append(str(r.inserted_id))

    db["hr_attendance_log"].delete_many({"company": DEMO_NAME})
    statuses = ["present", "present", "present", "absent", "present", "late"]
    for i, (sid, s) in enumerate(zip(staff_ids, STAFF)):
        db["hr_attendance_log"].insert_one({
            "company":    DEMO_NAME,
            "staff_id":   sid,
            "staff_name": s["name"],
            "date":       today,
            "status":     statuses[i],
            "method":     "manual",
            "created_at": now,
        })

    # ── Leave requests ────────────────────────────────────────────────────────
    db["hr_leave_requests"].delete_many({"company": DEMO_NAME})
    leave_data = [
        (0, "annual",  "2026-05-01", "2026-05-05", "approved",  "Rest after Q1 sprint"),
        (2, "sick",    "2026-04-22", "2026-04-23", "pending",   "Malaria treatment"),
        (4, "annual",  "2026-06-10", "2026-06-20", "pending",   "Family travel"),
    ]
    for (si, ltype, start, end, status, reason) in leave_data:
        db["hr_leave_requests"].insert_one({
            "company":    DEMO_NAME,
            "staff_id":   staff_ids[si],
            "staff_name": STAFF[si]["name"],
            "leave_type": ltype,
            "start_date": start,
            "end_date":   end,
            "status":     status,
            "reason":     reason,
            "created_at": now,
        })

    # ── PENCOM ────────────────────────────────────────────────────────────────
    db["hr_pencom_staff"].delete_many({"company": DEMO_NAME})
    for i, s in enumerate(STAFF):
        gross = s["salary"]
        employee_contrib = round(gross * 0.08)
        employer_contrib = round(gross * 0.10)
        db["hr_pencom_staff"].insert_one({
            "company":           DEMO_NAME,
            "staff_name":        s["name"],
            "pfa":               "Stanbic IBTC Pensions",
            "rsa_pin":           f"PEN{1000000 + i}",
            "monthly_salary":    gross,
            "employee_contrib":  employee_contrib,
            "employer_contrib":  employer_contrib,
            "total_contrib":     employee_contrib + employer_contrib,
            "last_remitted_month": "2026-03",
            "status":            "active",
            "created_at":        now,
        })

    # ── Probation ─────────────────────────────────────────────────────────────
    db["hr_probation"].delete_many({"company": DEMO_NAME})
    db["hr_probation"].insert_many([
        {
            "company":     DEMO_NAME,
            "staff_id":    staff_ids[5],
            "staff_name":  STAFF[5]["name"],
            "start_date":  (now - timedelta(days=83)).date().isoformat(),
            "end_date":    (now + timedelta(days=7)).date().isoformat(),
            "status":      "active",
            "notes":       "Review pending — manager to confirm extension or confirm.",
            "created_at":  now,
        },
        {
            "company":     DEMO_NAME,
            "staff_id":    staff_ids[2],
            "staff_name":  STAFF[2]["name"],
            "start_date":  (now - timedelta(days=15)).date().isoformat(),
            "end_date":    (now + timedelta(days=75)).date().isoformat(),
            "status":      "active",
            "notes":       "New hire — sales track.",
            "created_at":  now,
        },
    ])

    # ── Offboarding ───────────────────────────────────────────────────────────
    db["hr_offboarding"].delete_many({"company": DEMO_NAME})
    db["hr_offboarding"].insert_one({
        "company":       DEMO_NAME,
        "staff_name":    "Kelechi Mba",
        "role":          "Backend Developer",
        "exit_date":     (now + timedelta(days=14)).date().isoformat(),
        "reason":        "Resignation",
        "checklist":     {
            "laptop_returned":   False,
            "access_revoked":    False,
            "final_pay_cleared": False,
            "exit_interview":    True,
            "nda_signed":        True,
        },
        "created_at": now,
    })

    # ── Policy ────────────────────────────────────────────────────────────────
    db["hr_policies"].delete_many({"company": DEMO_NAME})
    db["hr_policies"].insert_one({
        "company":   DEMO_NAME,
        "filename":  "Employee Handbook v2.pdf",
        "content":   (
            "Remote Work Policy: Employees may work remotely up to 3 days per week with manager approval. "
            "Annual Leave: 20 working days per year. Sick Leave: 10 days per year with medical certificate. "
            "Probation: 3 months for all new hires. PENCOM: 8% employee, 10% employer contribution monthly. "
            "Dress Code: Smart casual Monday–Thursday; casual Friday. "
            "Notice Period: 1 month for staff, 2 months for management."
        ),
        "uploaded_at": now,
    })

    print(f"seeded: client={DEMO_NAME}")
    print(f"  staff={len(STAFF)}, leave=3, pencom={len(STAFF)}, probation=2, offboarding=1")
    print(f"  portal path=/portal/talent/{token}")
    return token


if __name__ == "__main__":
    import sys
    if "--wipe" in sys.argv:
        wipe()
    seed()
