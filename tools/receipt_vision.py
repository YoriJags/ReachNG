"""
Receipt Catcher — vision extraction.

Takes raw image bytes (a customer's bank-transfer screenshot from WhatsApp) and
returns structured fields: bank, amount, sender, reference, time, recipient.

Uses Claude Haiku 4.5 vision. Handles:
  - GTBank app / email
  - OPay, PalmPay, Kuda, Moniepoint
  - Access mobile / FirstMobile / Zenith mobile
  - POS slip photos
  - USSD confirmation screenshots
  - Receipt-like screenshots that aren't actually bank transfers (returns is_receipt=False)

Returns a `ReceiptData` Pydantic model. All fields optional except `is_receipt`.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Optional

import anthropic
import structlog
from pydantic import BaseModel, Field

from config import get_settings

log = structlog.get_logger()


# ─── Model ────────────────────────────────────────────────────────────────────

class ReceiptData(BaseModel):
    is_receipt: bool = Field(
        description="True if the image is a bank-transfer receipt / POS slip / "
                    "payment confirmation. False for menus, ID cards, selfies, "
                    "memes, anything not a payment artefact."
    )
    bank: Optional[str] = Field(default=None, description="Issuing bank or wallet (e.g. 'GTBank', 'OPay', 'Kuda')")
    amount_ngn: Optional[float] = Field(default=None, description="Naira amount. Strip ₦ and commas.")
    sender_name: Optional[str] = Field(default=None, description="Who sent the money (debit side)")
    sender_account: Optional[str] = Field(default=None, description="Sender account number, masked or full")
    recipient_name: Optional[str] = Field(default=None, description="Who received the money (credit side)")
    recipient_account: Optional[str] = Field(default=None, description="Recipient account number")
    recipient_bank: Optional[str] = Field(default=None, description="Recipient bank (often the client's bank)")
    reference: Optional[str] = Field(default=None, description="Transaction ref / session ID")
    transaction_time: Optional[str] = Field(default=None, description="Timestamp as shown on the receipt (verbatim)")
    status: Optional[str] = Field(default=None, description="'success' | 'pending' | 'failed' | None")
    confidence: float = Field(default=0.0, description="0.0-1.0 — how clearly the image reads as a receipt")
    extraction_notes: Optional[str] = Field(default=None, description="Anything unusual the model wants to flag")


# ─── Prompt ───────────────────────────────────────────────────────────────────

_VISION_SYSTEM = """You are a Nigerian banking-receipt OCR specialist.

You will be shown ONE image. Your job: decide if it is a payment/transfer receipt,
and if so, extract structured fields.

Common Nigerian receipt sources:
- GTBank: app, USSD, email confirmation
- OPay, PalmPay, Kuda, Moniepoint, Carbon — wallet apps
- Access Mobile, First Mobile, Zenith Mobile, UBA Mobile, Stanbic IBTC, FCMB, Sterling
- POS slips (Posera, Itex, Interswitch — small thermal-paper printouts)
- Bank-transfer email confirmations
- Print-screens of SMS debit alerts

NOT receipts: selfies, menus, ID cards, screenshots of chats, memes, location pins,
catalogues, photos of food, anything else. Return is_receipt=false for these.

When extracting:
- amount_ngn must be a number — strip ₦, commas, and currency words
- sender_name and recipient_name are people or business names as shown
- reference is the transaction ID / session ID / RRN — keep verbatim
- transaction_time is verbatim ("12 May 2026, 11:47pm" or "12/05/2026 23:47:12")
- confidence: 1.0 = crystal clear receipt with all fields. 0.5 = blurry/cropped but readable. <0.3 = barely legible.

Return ONLY a JSON object with these keys (no preamble, no markdown):
{
  "is_receipt": bool,
  "bank": string|null,
  "amount_ngn": number|null,
  "sender_name": string|null,
  "sender_account": string|null,
  "recipient_name": string|null,
  "recipient_account": string|null,
  "recipient_bank": string|null,
  "reference": string|null,
  "transaction_time": string|null,
  "status": "success"|"pending"|"failed"|null,
  "confidence": number,
  "extraction_notes": string|null
}
"""


# ─── Public API ───────────────────────────────────────────────────────────────

async def extract_receipt(image_bytes: bytes, mime_type: str,
                           client_id: Optional[str] = None) -> ReceiptData:
    """
    Run a Nigerian bank-receipt extraction over an image.

    `client_id` enables T0.2.5 metering — pass it from the webhook caller so
    every vision call is rate-limited + recorded against that client's bill.

    Synchronous Anthropic client wrapped — Anthropic Python SDK is sync, but the
    call is short enough to run inline. If we ever batch, move to AsyncAnthropic.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.warning("anthropic_key_missing_for_receipt_vision")
        return ReceiptData(is_receipt=False, confidence=0.0,
                           extraction_notes="ANTHROPIC_API_KEY not set")

    # T0.2.5 — anti-runaway rate-limit gate (20 vision calls/min per client)
    if client_id:
        try:
            from services.usage_meter import check_rate
            if not check_rate(str(client_id), "receipt"):
                log.warning("receipt_vision_rate_limited", client_id=client_id)
                return ReceiptData(is_receipt=False, confidence=0.0,
                                   extraction_notes="rate-limited by usage meter")
        except Exception:
            pass

    # Normalise mime — Anthropic accepts image/jpeg, image/png, image/gif, image/webp
    mime = (mime_type or "image/jpeg").lower().split(";")[0].strip()
    if mime not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        # Default to jpeg — most WhatsApp images compress to jpeg anyway
        mime = "image/jpeg"

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_VISION_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": "Extract receipt fields. Return ONLY the JSON object."},
                ],
            }],
        )
    except Exception as e:
        log.error("receipt_vision_call_failed", error=str(e))
        return ReceiptData(is_receipt=False, confidence=0.0,
                           extraction_notes=f"vision call failed: {e}")

    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()

    receipt = _parse_json_to_receipt(raw)

    # T0.2.5 — record successful usage event
    if client_id:
        try:
            from services.usage_meter import record
            record(
                client_id=str(client_id),
                feature="receipt",
                units=1,
                extra={"is_receipt": bool(receipt.is_receipt), "amount": receipt.amount_ngn},
            )
        except Exception:
            pass

    return receipt


def _parse_json_to_receipt(raw: str) -> ReceiptData:
    """Tolerantly parse Claude's JSON output into a ReceiptData."""
    # Strip code fences
    if raw.startswith("```"):
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
        if fence:
            raw = fence.group(1)

    # Fall back: find the outermost { ... }
    if not raw.startswith("{"):
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

    try:
        data = json.loads(raw)
    except Exception as e:
        log.warning("receipt_vision_parse_failed", error=str(e), raw_head=raw[:120])
        return ReceiptData(is_receipt=False, confidence=0.0,
                           extraction_notes=f"json parse failed: {e}")

    # Coerce amount_ngn to float — vision sometimes returns "₦45,000" or "45000.00"
    amt = data.get("amount_ngn")
    if isinstance(amt, str):
        cleaned = re.sub(r"[^\d.]", "", amt)
        try:
            data["amount_ngn"] = float(cleaned) if cleaned else None
        except ValueError:
            data["amount_ngn"] = None

    try:
        return ReceiptData(**data)
    except Exception as e:
        log.warning("receipt_data_validate_failed", error=str(e))
        return ReceiptData(is_receipt=False, confidence=0.0,
                           extraction_notes=f"validate failed: {e}")
