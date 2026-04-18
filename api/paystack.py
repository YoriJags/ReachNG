"""
Paystack — Nigerian payment processing for ReachNG client subscriptions.
Generates hosted payment links that clients pay via card/bank transfer/USSD.
"""
import uuid
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import get_settings

router = APIRouter(prefix="/paystack", tags=["Paystack"])

PAYSTACK_BASE = "https://api.paystack.co"


class PaymentLinkRequest(BaseModel):
    client_name: str
    email: str
    amount_ngn: int
    plan_label: str = "Monthly Subscription"
    callback_url: Optional[str] = None


@router.post("/initialize")
async def initialize_payment(payload: PaymentLinkRequest):
    """
    Generate a Paystack payment link for a client's subscription.
    Returns a URL the owner sends to the client via WhatsApp.
    Amount is in Naira — converted to kobo for Paystack.
    """
    settings = get_settings()
    if not settings.paystack_secret_key:
        raise HTTPException(503, "PAYSTACK_SECRET_KEY not configured")

    reference = f"RNG-{uuid.uuid4().hex[:10].upper()}"
    amount_kobo = payload.amount_ngn * 100

    body = {
        "email":       payload.email,
        "amount":      amount_kobo,
        "reference":   reference,
        "currency":    "NGN",
        "metadata": {
            "client_name": payload.client_name,
            "plan":        payload.plan_label,
            "custom_fields": [
                {"display_name": "Client", "variable_name": "client_name", "value": payload.client_name},
                {"display_name": "Plan",   "variable_name": "plan",        "value": payload.plan_label},
            ],
        },
    }
    if payload.callback_url:
        body["callback_url"] = payload.callback_url

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=body,
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type":  "application/json",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Paystack error: {resp.text}")

    data = resp.json()
    if not data.get("status"):
        raise HTTPException(502, data.get("message", "Paystack returned error"))

    return {
        "reference":   reference,
        "payment_url": data["data"]["authorization_url"],
        "amount_ngn":  payload.amount_ngn,
        "client":      payload.client_name,
    }


@router.get("/verify/{reference}")
async def verify_payment(reference: str):
    """Check if a Paystack payment was completed. Call this from webhook or manually."""
    settings = get_settings()
    if not settings.paystack_secret_key:
        raise HTTPException(503, "PAYSTACK_SECRET_KEY not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Paystack error: {resp.text}")

    data = resp.json().get("data", {})
    paid = data.get("status") == "success"

    return {
        "reference": reference,
        "paid":      paid,
        "status":    data.get("status"),
        "amount_ngn": (data.get("amount", 0) // 100),
        "paid_at":   data.get("paid_at"),
        "channel":   data.get("channel"),
    }
