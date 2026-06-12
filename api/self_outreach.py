"""
Self-outreach preview API (admin Basic Auth).

Lets the operator generate dry-run copy previews from the Control Tower
without dropping into the CLI. NO sends, NO HITL queue, NO Mongo writes —
purely the drafter output as JSON.

Routes:
  POST /api/v1/admin/self-outreach/dry-run
    body: optional {samples: [...]} — when empty, uses 5 baked-in Lagos profiles
    returns: {drafts: [{label, subject, message, word_count, error?}], cost_ngn}

  POST /api/v1/admin/self-outreach/preview-one
    body: {business_name, vertical, address?, category?, rating?, reviews_excerpt?,
           contact_name?, contact_title?, website?, contact_id?}
    returns: {subject, message, word_count}
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth
from services.reachng_self_outreach import draft_with_link


router = APIRouter(prefix="/api/v1/admin/self-outreach",
                   tags=["SelfOutreach"],
                   dependencies=[Depends(require_auth)])


# Same 5 baked-in samples as scripts/dry_run_outreach.py. Mix of rich vs
# sparse enrichment so we stress-test how the drafter handles both.
BAKED_SAMPLES = [
    {
        "label":         "1 · Premium hospitality (Victoria Island)",
        "business_name": "Cocoon Lagos",
        "vertical":      "hospitality",
        "address":       "Eko Atlantic, Victoria Island, Lagos",
        "category":      "Rooftop restaurant & lounge",
        "rating":        4.6,
        "reviews_excerpt": "Food and view are 10/10 but they took 4 hours to confirm my reservation on a Saturday. Lost patience and went to Cantonese.",
        "contact_name":  "Adunni Okafor",
        "contact_title": "General Manager",
        "website":       "https://cocoon.ng",
        "contact_id":    "demo_cocoon",
    },
    {
        "label":         "2 · Luxury real estate (Banana Island)",
        "business_name": "Sandhill Properties",
        "vertical":      "real_estate",
        "address":       "1 Adeola Odeku, Ikoyi, Lagos",
        "category":      "Estate agent · luxury residential",
        "rating":        4.8,
        "reviews_excerpt": "Excellent agents but PoF verification took 9 days — I had moved on by then.",
        "contact_name":  "Tunde Bakare",
        "contact_title": "Managing Partner",
        "website":       "https://sandhillproperties.ng",
        "contact_id":    "demo_sandhill",
    },
    {
        "label":         "3 · Boutique law firm (Ikoyi) — sparse enrichment",
        "business_name": "Akinwale & Co.",
        "vertical":      "professional_services",
        "address":       "Awolowo Road, Ikoyi, Lagos",
        "category":      "Boutique law firm",
        "rating":        4.4,
        "reviews_excerpt": None,
        "contact_name":  None,
        "contact_title": None,
        "website":       "https://akinwaleandco.com",
        "contact_id":    "demo_akinwale",
    },
    {
        "label":         "4 · Aesthetic clinic (Lekki Phase 1)",
        "business_name": "Mira Aesthetics",
        "vertical":      "clinics",
        "address":       "Admiralty Way, Lekki Phase 1, Lagos",
        "category":      "Skin & aesthetic clinic",
        "rating":        4.7,
        "reviews_excerpt": "Amazing facials but the WhatsApp number never responds outside 9-5. Try DM-ing for a Saturday slot — good luck.",
        "contact_name":  "Dr. Mira Adesina",
        "contact_title": "Founder",
        "website":       "https://miraaesthetics.ng",
        "contact_id":    "demo_mira",
    },
    {
        "label":         "5 · Fashion atelier (Yaba)",
        "business_name": "Adire by Tomi",
        "vertical":      "small_business",
        "address":       "Herbert Macaulay Way, Yaba, Lagos",
        "category":      "Adire & ready-to-wear atelier",
        "rating":        4.9,
        "reviews_excerpt": "Beautiful pieces but answering DMs is slow — I waited 2 weeks for a quote on a wedding order.",
        "contact_name":  "Tomi Adeyemi",
        "contact_title": "Owner",
        "website":       "https://adirebytomi.com",
        "contact_id":    "demo_tomi",
    },
]


class Sample(BaseModel):
    label:           Optional[str] = None
    business_name:   str           = Field(min_length=1, max_length=120)
    vertical:        str           = "general"
    address:         Optional[str] = None
    category:        Optional[str] = None
    rating:          Optional[float] = None
    reviews_excerpt: Optional[str] = None
    contact_name:    Optional[str] = None
    contact_title:   Optional[str] = None
    website:         Optional[str] = None
    contact_id:      Optional[str] = None


class DryRunPayload(BaseModel):
    samples: Optional[list[Sample]] = None


@router.post("/dry-run")
async def dry_run(payload: Optional[DryRunPayload] = None):
    """Generate drafts for 5 baked-in profiles (or supplied list). Nothing sends."""
    samples_in = (payload.samples if payload and payload.samples else None)
    if samples_in:
        samples = [s.model_dump() for s in samples_in]
    else:
        samples = [dict(s) for s in BAKED_SAMPLES]

    drafts = []
    cost_units = 0
    for s in samples:
        label = s.pop("label", None) or s.get("business_name") or "(unnamed)"
        row = {"label": label,
               "business_name": s.get("business_name"),
               "vertical":      s.get("vertical")}
        try:
            out = draft_with_link(**s)
            row["subject"]    = out["subject"]
            row["message"]    = out["message"]
            row["word_count"] = len([w for w in (out["message"] or "").split() if w])
            cost_units += 1
        except Exception as e:
            row["error"] = str(e)
        drafts.append(row)

    return {
        "drafts":       drafts,
        "count":        len(drafts),
        "cost_ngn_est": round(cost_units * 4.0, 2),  # ~₦4 per Haiku draft
    }


@router.post("/preview-one")
async def preview_one(sample: Sample):
    """Generate a single draft. Useful for tuning a real prospect."""
    fields = sample.model_dump()
    fields.pop("label", None)
    try:
        out = draft_with_link(**fields)
    except Exception as e:
        raise HTTPException(502, f"Drafter failed: {e}")
    out["word_count"] = len([w for w in (out["message"] or "").split() if w])
    return out


@router.get("/reply-poll")
async def reply_poll_state():
    """Stop-on-reply watchdog state for the admin UI: is the IMAP poller
    configured, and what did the last run see. No Railway logs required."""
    from services.outreach_reply_poll import reply_poll_status
    return reply_poll_status()


@router.post("/reply-poll/run")
async def reply_poll_run_now():
    """Run the reply poll immediately (the scheduler also runs it every 10
    minutes). Blocking IMAP work goes off the event loop."""
    import asyncio
    from services.outreach_reply_poll import poll_outreach_replies, reply_poll_status
    result = await asyncio.get_event_loop().run_in_executor(None, poll_outreach_replies)
    return {"result": result, **reply_poll_status()}
