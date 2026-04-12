"""
School Fee Reminder & Receipt System — Product #2 on ReachNG platform.

Schools register, upload student/parent data, and the system:
- Sends WhatsApp reminders (30, 14, 7 days before deadline)
- Provides Paystack payment links per student
- Records payments and generates receipts
- Gives the bursar a live dashboard

Collections (MongoDB):
  sf_schools   — registered schools
  sf_students  — students + parent contact per school
  sf_payments  — payment records
"""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db

router = APIRouter(prefix="/school-fees", tags=["School Fees"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _db():
    return get_db()

def _schools():
    return _db()["sf_schools"]

def _students():
    return _db()["sf_students"]

def _payments():
    return _db()["sf_payments"]

def _serial(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc

def ensure_school_fees_indexes():
    _schools().create_index("name")
    _students().create_index([("school_id", 1), ("parent_phone", 1)])
    _payments().create_index([("student_id", 1), ("paid_at", -1)])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SchoolUpsert(BaseModel):
    name: str                               # e.g. "Greenfield International School"
    city: str = "Lagos"
    contact_name: str                       # Bursar / proprietor name
    contact_phone: str                      # Bursar WhatsApp
    contact_email: Optional[str] = None
    paystack_public_key: Optional[str] = None
    active: bool = True
    # WhatsApp provider — each school can send from their own number
    whatsapp_provider: str = "unipile"      # "unipile" | "meta"
    whatsapp_account_id: Optional[str] = None  # Unipile account id for this school
    meta_phone_number_id: Optional[str] = None # From Meta Business Manager
    meta_access_token: Optional[str] = None    # Permanent system user token


class StudentUpsert(BaseModel):
    school_id: str
    student_name: str
    class_name: str                         # e.g. "JSS 2B"
    parent_name: str
    parent_phone: str                       # E.164 format
    parent_email: Optional[str] = None
    fee_amount: float                       # in Naira
    fee_label: str = "Term Fees"            # e.g. "First Term 2025/2026 Fees"
    due_date: str                           # ISO date string: "2026-01-15"
    active: bool = True


class RecordPayment(BaseModel):
    student_id: str
    amount_paid: float
    payment_method: str = "paystack"        # paystack | cash | transfer
    reference: Optional[str] = None
    note: Optional[str] = None


class SendReminders(BaseModel):
    school_id: str
    dry_run: bool = True


# ─── Schools ──────────────────────────────────────────────────────────────────

@router.get("/schools")
async def list_schools():
    schools = list(_schools().find({}).sort("name", 1))
    return [_serial(s) for s in schools]


@router.get("/schools/{school_id}")
async def get_school(school_id: str):
    school = _schools().find_one({"_id": ObjectId(school_id)})
    if not school:
        raise HTTPException(404, "School not found")
    return _serial(school)


@router.post("/schools")
async def upsert_school(payload: SchoolUpsert):
    now = datetime.now(timezone.utc)
    result = _schools().update_one(
        {"name": {"$regex": f"^{re.escape(payload.name)}$", "$options": "i"}},
        {
            "$set": {
                "name": payload.name,
                "city": payload.city,
                "contact_name": payload.contact_name,
                "contact_phone": payload.contact_phone,
                "contact_email": payload.contact_email,
                "paystack_public_key": payload.paystack_public_key,
                "active": payload.active,
                "whatsapp_provider": payload.whatsapp_provider,
                "whatsapp_account_id": payload.whatsapp_account_id,
                "meta_phone_number_id": payload.meta_phone_number_id,
                "meta_access_token": payload.meta_access_token,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    action = "created" if result.upserted_id else "updated"
    return {"success": True, "action": action, "school": payload.name}


@router.delete("/schools/{school_id}")
async def deactivate_school(school_id: str):
    result = _schools().update_one(
        {"_id": ObjectId(school_id)},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "School not found")
    return {"success": True, "status": "deactivated"}


# ─── Students ─────────────────────────────────────────────────────────────────

@router.get("/schools/{school_id}/students")
async def list_students(school_id: str, paid: Optional[bool] = None):
    query: dict = {"school_id": school_id}
    if paid is not None:
        query["paid"] = paid
    students = list(_students().find(query).sort("student_name", 1))
    return [_serial(s) for s in students]


@router.post("/schools/{school_id}/students")
async def upsert_student(school_id: str, payload: StudentUpsert):
    if payload.school_id != school_id:
        raise HTTPException(400, "school_id mismatch")
    now = datetime.now(timezone.utc)
    result = _students().update_one(
        {
            "school_id": school_id,
            "parent_phone": payload.parent_phone,
            "fee_label": payload.fee_label,
        },
        {
            "$set": {
                "school_id": school_id,
                "student_name": payload.student_name,
                "class_name": payload.class_name,
                "parent_name": payload.parent_name,
                "parent_phone": payload.parent_phone,
                "parent_email": payload.parent_email,
                "fee_amount": payload.fee_amount,
                "fee_label": payload.fee_label,
                "due_date": payload.due_date,
                "active": payload.active,
                "updated_at": now,
            },
            "$setOnInsert": {
                "paid": False,
                "amount_paid": 0.0,
                "reminder_count": 0,
                "created_at": now,
            },
        },
        upsert=True,
    )
    action = "created" if result.upserted_id else "updated"
    return {"success": True, "action": action}


# ─── Payments ─────────────────────────────────────────────────────────────────

@router.post("/payments/record")
async def record_payment(payload: RecordPayment):
    student = _students().find_one({"_id": ObjectId(payload.student_id)})
    if not student:
        raise HTTPException(404, "Student not found")

    now = datetime.now(timezone.utc)
    total_paid = student.get("amount_paid", 0.0) + payload.amount_paid
    fully_paid = total_paid >= student["fee_amount"]

    _students().update_one(
        {"_id": ObjectId(payload.student_id)},
        {
            "$set": {
                "amount_paid": total_paid,
                "paid": fully_paid,
                "paid_at": now if fully_paid else None,
                "updated_at": now,
            }
        },
    )

    _payments().insert_one({
        "student_id": payload.student_id,
        "school_id": student["school_id"],
        "student_name": student["student_name"],
        "parent_phone": student["parent_phone"],
        "amount_paid": payload.amount_paid,
        "total_paid": total_paid,
        "fee_amount": student["fee_amount"],
        "fully_paid": fully_paid,
        "payment_method": payload.payment_method,
        "reference": payload.reference,
        "note": payload.note,
        "paid_at": now,
    })

    return {
        "success": True,
        "fully_paid": fully_paid,
        "amount_paid": total_paid,
        "balance": max(0, student["fee_amount"] - total_paid),
    }


@router.get("/schools/{school_id}/payments")
async def list_payments(school_id: str, limit: int = 100):
    payments = list(
        _payments().find({"school_id": school_id})
        .sort("paid_at", -1)
        .limit(limit)
    )
    return [_serial(p) for p in payments]


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.get("/schools/{school_id}/stats")
async def school_stats(school_id: str):
    students = list(_students().find({"school_id": school_id, "active": True}))
    total = len(students)
    paid = sum(1 for s in students if s.get("paid"))
    outstanding_amount = sum(
        max(0, s["fee_amount"] - s.get("amount_paid", 0))
        for s in students if not s.get("paid")
    )
    collected_amount = sum(s.get("amount_paid", 0) for s in students)
    return {
        "total_students": total,
        "paid": paid,
        "outstanding": total - paid,
        "collection_rate": round(paid / total * 100, 1) if total else 0,
        "collected_amount": collected_amount,
        "outstanding_amount": outstanding_amount,
    }


@router.get("/stats")
async def platform_stats():
    """Aggregate stats across all schools — for dashboard overview."""
    schools = list(_schools().find({"active": True}))
    school_ids = [str(s["_id"]) for s in schools]
    students = list(_students().find({"school_id": {"$in": school_ids}, "active": True}))
    total = len(students)
    paid = sum(1 for s in students if s.get("paid"))
    collected = sum(s.get("amount_paid", 0) for s in students)
    outstanding = sum(
        max(0, s["fee_amount"] - s.get("amount_paid", 0))
        for s in students if not s.get("paid")
    )
    return {
        "active_schools": len(schools),
        "total_students": total,
        "paid_students": paid,
        "outstanding_students": total - paid,
        "collection_rate": round(paid / total * 100, 1) if total else 0,
        "total_collected": collected,
        "total_outstanding": outstanding,
    }


# ─── Reminders ────────────────────────────────────────────────────────────────

@router.post("/reminders/send")
async def send_reminders(payload: SendReminders):
    """
    Send WhatsApp reminders to parents who haven't paid.
    In dry_run mode: returns who would be messaged without sending.
    """
    from tools.outreach import send_whatsapp_for_client

    school = _schools().find_one({"_id": ObjectId(payload.school_id)})
    if not school:
        raise HTTPException(404, "School not found")

    unpaid = list(_students().find({
        "school_id": payload.school_id,
        "paid": False,
        "active": True,
    }))

    results = []

    for student in unpaid:
        due = student.get("due_date", "")
        balance = max(0, student["fee_amount"] - student.get("amount_paid", 0))
        message = (
            f"Dear {student['parent_name']},\n\n"
            f"This is a reminder that {student['student_name']}'s {student['fee_label']} "
            f"of ₦{balance:,.0f} is due on {due}.\n\n"
            f"Kindly make payment to avoid any disruption to your child's schooling.\n\n"
            f"Thank you,\n{school['name']}"
        )

        if payload.dry_run:
            results.append({
                "student": student["student_name"],
                "parent": student["parent_name"],
                "phone": student["parent_phone"],
                "balance": balance,
                "message_preview": message[:120] + "...",
            })
        else:
            try:
                # Routes to school's Meta number or Unipile account — same pattern as outreach clients
                await send_whatsapp_for_client(
                    phone=student["parent_phone"],
                    message=message,
                    client_doc=school,  # school doc has whatsapp_provider, meta_phone_number_id, meta_access_token
                )
                _students().update_one(
                    {"_id": student["_id"]},
                    {
                        "$inc": {"reminder_count": 1},
                        "$set": {"last_reminder_at": datetime.now(timezone.utc)},
                    },
                )
                results.append({"student": student["student_name"], "sent": True})
            except Exception as e:
                results.append({"student": student["student_name"], "sent": False, "error": str(e)})

    return {
        "dry_run": payload.dry_run,
        "school": school["name"],
        "reminders_queued": len(results),
        "results": results,
    }
