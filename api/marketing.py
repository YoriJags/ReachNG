"""
Public marketing site - landing, pricing, how-it-works, about, contact, vertical landers.
Also handles self-serve signup -> Paystack -> auto-provision flow.
"""
import hmac
import hashlib
import secrets as pysecrets
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, RedirectResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
import structlog

from config import get_settings
from database import get_db
from services.marketing_content import get_vertical_content, list_canonical_slugs
from services.analytics import (
    track_page_viewed, track_vertical_lander, track_contact_submitted,
    track_signup_page, track_signup_initiated,
    track_payment_verified, track_client_provisioned,
    track_signup_failed, track_paystack_webhook_ignored,
)

log = structlog.get_logger()
router = APIRouter(tags=["Marketing"])

PAYSTACK_BASE = "https://api.paystack.co"

PLAN_PRICING = {
    "starter": {"label": "Solo",   "ngn":  60_000},
    "growth":  {"label": "Team",   "ngn": 120_000},
    "scale":   {"label": "Empire", "ngn": 250_000},
}


def _live_pricing() -> dict:
    try:
        from services.platform_settings import get_plan_pricing
        return get_plan_pricing()
    except Exception:
        return PLAN_PRICING


def _templates(request: Request):
    return request.app.state.templates


# ─── Cover personalization — scene packs per vertical ────────────────────────
# Each pack swaps the hero HITL mock content. Cookie `reachng_vertical` set by
# /set-vertical/{slug} drives the lookup. Default = hospitality so cold organic
# traffic keeps its current Lagos venue scene.
SCENE_PACKS = {
    "hospitality": {
        "slug": "hospitality",
        "label": "Restaurants & venues",
        "label_emoji": "🍽 Restaurants & venues",
        "demo_url": "/portal/demo/hospitality",
        "customer_name": "Funke Adebayo",
        "customer_initials": "FA",
        "avatar_grad": "linear-gradient(135deg,#a8e6cf,#56cfa1)",
        "avatar_text_color": "#0a3d2a",
        "voice_duration": "0:34",
        "transcript": "\"Hi, I want to book your rooftop for Saturday around 9pm, table of 6. It's my friend's birthday. Do you still have something near the DJ booth, and how much is the deposit?\"",
        "classifier_verdict": "🔥 HOT · qualifying",
        "transcribe_sec": "2.4",
        "biz_name": "Altitude Lagos",
        "draft_text": "Hey Funke! Yes, we have one DJ-booth table left for Saturday 9pm, perfect for 6. Bottle minimum is ₦180,000 and we hold the table with a ₦90,000 deposit.\n\nSend to GTBank · 0123456789 · Altitude Lagos Ltd and screenshot back. Table is locked the moment it lands. 🎉",
        "examples": [
            "Table for 6 Saturday 9pm — birthday",
            "Bottle service for 4, this Friday",
            "Brunch for 8 Sunday — any garden tables?",
        ],
        "input_placeholder": "Hi, do you still have a table for 6 this Saturday around 9pm? It's my friend's birthday.",
    },
    "real_estate": {
        "slug": "real_estate",
        "label": "Real estate",
        "label_emoji": "🏛 Real estate",
        "demo_url": "/portal/demo/real_estate",
        "customer_name": "Tunde Bakare",
        "customer_initials": "TB",
        "avatar_grad": "linear-gradient(135deg,#d4b896,#a8845c)",
        "avatar_text_color": "#3d2812",
        "voice_duration": "0:42",
        "transcript": "\"Hi, I saw your listing for the 5-bedroom in Banana Island on Instagram. Budget is around ₦650M. Is it still on the market? Can I view this Saturday?\"",
        "classifier_verdict": "🔥 HOT · qualifying",
        "transcribe_sec": "2.7",
        "biz_name": "Sapphire Estates",
        "draft_text": "Hi Tunde, yes the Banana Island 5-bedroom is still available — ₦680M asking, all-in. Quick PoF check first (standard — just confirms budget), then I can lock a Saturday viewing window for you.\n\nSend a short bank statement or PoF letter via WhatsApp here, I'll confirm your slot today. 🏛",
        "examples": [
            "5-bed Banana Island — ₦650M, can I view?",
            "1-bed Lekki Phase 1 short-let, December",
            "Off-plan Ikoyi — payment plan options?",
        ],
        "input_placeholder": "Hi, saw the listing for the 5-bedroom in Banana Island. Budget around ₦650M. Can I view this Saturday?",
    },
    "professional_services": {
        "slug": "professional_services",
        "label": "Law & advisory",
        "label_emoji": "⚖ Law & advisory",
        "demo_url": "/portal/demo/professional_services",
        "customer_name": "Olumide Kareem",
        "customer_initials": "OK",
        "avatar_grad": "linear-gradient(135deg,#b8c5d1,#5a7185)",
        "avatar_text_color": "#0f1e2c",
        "voice_duration": "0:28",
        "transcript": "\"Good evening. I run a fintech and just got a CBN compliance notice on our agency banking license. Need a quick consult — can we talk this weekend?\"",
        "classifier_verdict": "🔥 HOT · qualifying",
        "transcribe_sec": "2.2",
        "biz_name": "Adesina & Co",
        "draft_text": "Hi Olumide, sorry to hear that — CBN agency-banking notices are time-sensitive, glad you reached out. Quick conflict check first: anyone at your firm currently in contention with our existing clients? (Just yes / no.)\n\nIf clear, I can lock you in for a 45-min consult Saturday morning. Retainer for initial response is ₦450k. ⚖",
        "examples": [
            "CBN compliance notice — urgent consult",
            "Tenancy dispute — Lagos State, need advice",
            "M&A diligence — fintech, NDA needed first",
        ],
        "input_placeholder": "Good evening. I run a fintech and just got a CBN compliance notice. Need a consult this weekend.",
    },
    "education": {
        "slug": "education",
        "label": "Schools",
        "label_emoji": "🎓 Schools",
        "demo_url": "/portal/demo/education",
        "customer_name": "Ngozi Eze",
        "customer_initials": "NE",
        "avatar_grad": "linear-gradient(135deg,#f5c2c7,#d96878)",
        "avatar_text_color": "#4a1018",
        "voice_duration": "0:38",
        "transcript": "\"Hello, I'm writing from London about Year 7 admission for September. My daughter currently attends a school in Hampstead. Is the prospectus on your website current?\"",
        "classifier_verdict": "🔥 HOT · qualifying",
        "transcribe_sec": "2.5",
        "biz_name": "Lagoon British International",
        "draft_text": "Good morning Mrs Eze, thank you for reaching out from London. The September Year 7 cohort still has spaces — we'll send the up-to-date 2026 prospectus + fee schedule (₦8.5M/term, all-in) to your inbox tonight.\n\nQuick first step: any safeguarding records or current school reports we should review? Reply here with attachments any time. 🎓",
        "examples": [
            "Year 7 admission, September — diaspora",
            "School fees plan for SS2 — can we phase?",
            "Bus route from Lekki Phase 2 — available?",
        ],
        "input_placeholder": "Hello, writing from London about Year 7 admission for September. Is the prospectus current?",
    },
    "small_business": {
        "slug": "small_business",
        "label": "Beauty & wellness",
        "label_emoji": "✨ Beauty & wellness",
        "demo_url": "/portal/demo/small_business",
        "customer_name": "Chiamaka Okeke",
        "customer_initials": "CO",
        "avatar_grad": "linear-gradient(135deg,#fde2a8,#e8a93b)",
        "avatar_text_color": "#5c3a08",
        "voice_duration": "0:25",
        "transcript": "\"Hi, I want to book a full hair appointment + manicure for Saturday afternoon. Last time was perfect — same stylist if possible?\"",
        "classifier_verdict": "🔥 HOT · returning",
        "transcribe_sec": "2.0",
        "biz_name": "Glow Studio Lagos",
        "draft_text": "Welcome back Chiamaka! 🙌 Yes, Tola has Saturday 2:30pm and 4:00pm open — both 90 mins (hair + manicure). Deposit to lock is ₦15,000.\n\nSend to OPay · 8101234567 · Glow Studio and reply with your slot. ✨",
        "examples": [
            "Hair appointment Saturday — same stylist?",
            "Full massage + facial, this weekend",
            "Manicure for a wedding — Friday morning",
        ],
        "input_placeholder": "Hi, I'd love to book a full hair appointment + manicure for Saturday afternoon.",
    },
}


# ─── Wave 2 scene packs — per-vertical Three Jobs scenes (Tone / Receipt / Brief)
# These overlay onto SCENE_PACKS at render time. Keys map to the three scene
# blocks on the landing's 'Three jobs' section. Used to stop a real-estate
# visitor seeing a restaurant scene mid-scroll.
WAVE2_SCENES = {
    "hospitality": {
        "tone": {
            "customer_q": "Hi, do you still have a table for 6 this Saturday?",
            "draft_reply": "Hey Funke 🙌 yes, we still have one 9pm table for 6 near the DJ booth. Deposit is ₦90k to lock it. Want me to hold it for 10 mins?",
            "time_label": "Saturday · 8:42 PM",
        },
        "receipt": {
            "customer_name": "Bola Olajide", "customer_initials": "BO",
            "avatar_grad": "linear-gradient(135deg,#fce4a8,#f5b942)", "avatar_text_color": "#7a4a00",
            "phone_masked": "+234 802 ••• 89", "time_label": "11:23 AM",
            "bank": "GTBank", "amount_naira": "450,000", "amount_short": "₦450k",
            "from_name_caps": "BOLA O. OLAJIDE", "to_name_caps": "ALTITUDE LAGOS LTD",
            "ref": "Table booking Sat", "datetime_label": "17 May 2026 · 11:22:48",
            "biz_name": "Altitude Lagos",
            "match_line": "booking #ALT-2614 · Funke + 5 · Saturday 9pm DJ booth · ₦450k deposit",
            "draft_reply": "Hey Bola, thanks for the screenshot 🙏 I'll lock in your Saturday 9pm booking (booth near the DJ, table of 6) the moment ₦450k reflects on our end (usually under 10 mins). I'll ping you the second it lands.",
        },
        "brief": {
            "day_label": "SATURDAY · 7:02 AM",
            "headline": "12 conversations held · 8 drafts ready · 2 🔥 need your tap",
            "money_label": "💰 ₦450k collected",
            "money_detail": "Bola Olajide · GTB transfer · matched to Saturday booking",
            "hot_lines": [
                "Funke A. · table of 6, Sat 9pm DJ booth",
                "Tunde K. · ₦12M apartment viewing request",
            ],
            "leak_alert": "Adunni Properties · 2 unanswered enquiries since Friday night. Drafts ready.",
            "slowest_reply": "4 min (vs 6 hrs before ReachNG)",
        },
    },
    "real_estate": {
        "tone": {
            "customer_q": "Hi, is the 5-bed in Banana Island still available?",
            "draft_reply": "Hi Tunde, yes — still available at ₦680M asking. Quick PoF check first (standard), then I lock a Saturday viewing window. Share a short bank statement here and I'll confirm your slot today. 🏛",
            "time_label": "Friday · 9:14 PM",
        },
        "receipt": {
            "customer_name": "Tunde Bakare", "customer_initials": "TB",
            "avatar_grad": "linear-gradient(135deg,#d4b896,#a8845c)", "avatar_text_color": "#3d2812",
            "phone_masked": "+234 803 ••• 17", "time_label": "10:08 AM",
            "bank": "Access Bank", "amount_naira": "5,000,000", "amount_short": "₦5M",
            "from_name_caps": "TUNDE A. BAKARE", "to_name_caps": "SAPPHIRE ESTATES LTD",
            "ref": "Banana Island earnest", "datetime_label": "21 May 2026 · 10:07:32",
            "biz_name": "Sapphire Estates",
            "match_line": "lead #SE-0418 · Tunde Bakare · 5-bed Banana Island · ₦680M asking · earnest tier",
            "draft_reply": "Hi Tunde, ₦5M earnest received — thank you 🏛 I'll lock the viewing for Saturday 10am once it reflects on our end. PoF clean, I'll send the access code + parking pass an hour before.",
        },
        "brief": {
            "day_label": "MONDAY · 7:02 AM",
            "headline": "9 enquiries held · 6 drafts ready · 3 🔥 need your tap",
            "money_label": "💰 ₦5M earnest received",
            "money_detail": "Tunde Bakare · Access transfer · matched to Banana Island lead",
            "hot_lines": [
                "Adekunle O. · Lekki off-plan, ₦180M, asking for payment plan",
                "Mrs Edet · short-let December Eko Atlantic, family of 4",
            ],
            "leak_alert": "Ikoyi maisonette · 2 unanswered enquiries since Saturday. Drafts ready.",
            "slowest_reply": "6 min (vs 9 hrs before ReachNG)",
        },
    },
    "professional_services": {
        "tone": {
            "customer_q": "Good evening — can I get a quick consult this weekend?",
            "draft_reply": "Hi Olumide, glad you reached out. Quick conflict check first: anyone at your firm currently in contention with our existing clients? If clear, I'll lock a 45-min slot Saturday morning. Retainer for initial response is ₦450k. ⚖",
            "time_label": "Friday · 6:48 PM",
        },
        "receipt": {
            "customer_name": "Olumide Kareem", "customer_initials": "OK",
            "avatar_grad": "linear-gradient(135deg,#b8c5d1,#5a7185)", "avatar_text_color": "#0f1e2c",
            "phone_masked": "+234 805 ••• 02", "time_label": "9:46 AM",
            "bank": "Zenith Bank", "amount_naira": "450,000", "amount_short": "₦450k",
            "from_name_caps": "OLUMIDE A. KAREEM", "to_name_caps": "ADESINA & CO. SOLICITORS",
            "ref": "Retainer — CBN response", "datetime_label": "22 May 2026 · 09:45:18",
            "biz_name": "Adesina & Co",
            "match_line": "matter #AC-2026-0211 · Olumide Kareem · CBN agency-banking response · retainer phase",
            "draft_reply": "Hi Olumide, retainer received — thank you ⚖ I'll confirm the Saturday 10am slot once funds reflect. We'll send a brief intake form for your records and the call link an hour before.",
        },
        "brief": {
            "day_label": "MONDAY · 7:02 AM",
            "headline": "11 enquiries reviewed · 5 drafts ready · 2 🔥 need your tap",
            "money_label": "💰 ₦450k retainer in",
            "money_detail": "Olumide Kareem · Zenith transfer · matched to CBN matter",
            "hot_lines": [
                "Mrs Adeola · tenancy dispute Lekki, hearing next Thursday",
                "Bayo I. (fintech CEO) · M&A diligence, NDA outstanding",
            ],
            "leak_alert": "Solicitor enquiry · 3 days, no response. Conflict check still open.",
            "slowest_reply": "8 min (vs Monday-9am before ReachNG)",
        },
    },
    "education": {
        "tone": {
            "customer_q": "Hello, do you still have spaces for Year 7 in September?",
            "draft_reply": "Good morning Mrs Eze, yes — September Year 7 cohort still has spaces. We'll send the 2026 prospectus + fee schedule (₦8.5M/term, all-in) to your inbox tonight. Any current school reports we should review? Reply here with attachments any time. 🎓",
            "time_label": "Wednesday · 4:12 PM",
        },
        "receipt": {
            "customer_name": "Ngozi Eze", "customer_initials": "NE",
            "avatar_grad": "linear-gradient(135deg,#f5c2c7,#d96878)", "avatar_text_color": "#4a1018",
            "phone_masked": "+44 7700 ••• 41", "time_label": "8:55 AM",
            "bank": "First Bank", "amount_naira": "200,000", "amount_short": "₦200k",
            "from_name_caps": "NGOZI A. EZE", "to_name_caps": "LAGOON BIS LTD",
            "ref": "Application fee — Y7 Sept", "datetime_label": "23 May 2026 · 08:54:07",
            "biz_name": "Lagoon British International",
            "match_line": "application #LB-2026-0118 · Ngozi Eze · Year 7 September · diaspora (London)",
            "draft_reply": "Good morning Mrs Eze, application fee received — thank you 🎓 We'll confirm the Saturday assessment slot once funds reflect and send the family pack to your inbox tonight. Any preferred time-window for the assessment? Diaspora calls Mon/Fri only.",
        },
        "brief": {
            "day_label": "TUESDAY · 7:02 AM",
            "headline": "18 admissions enquiries · 9 drafts ready · 4 🔥 need your tap",
            "money_label": "💰 ₦200k application fee in",
            "money_detail": "Ngozi Eze (London) · First Bank · matched to Y7 application",
            "hot_lines": [
                "Mr Adesina · SS2 transfer, asking for fee plan",
                "The Okafors (Atlanta) · Year 9 + Year 5 sibling discount enquiry",
            ],
            "leak_alert": "Year 10 enquiry from Houston · 4 days no response. Time-zone draft ready.",
            "slowest_reply": "12 min (vs next-day before ReachNG)",
        },
    },
    "small_business": {
        "tone": {
            "customer_q": "Hi, can I book a full hair appointment + manicure Saturday?",
            "draft_reply": "Welcome back Chiamaka 🙌 Tola has Saturday 2:30pm or 4:00pm open — both 90 mins (hair + manicure). Deposit to lock is ₦15k. Send to OPay · 8101234567 · Glow Studio and reply with your slot. ✨",
            "time_label": "Thursday · 7:21 PM",
        },
        "receipt": {
            "customer_name": "Chiamaka Okeke", "customer_initials": "CO",
            "avatar_grad": "linear-gradient(135deg,#fde2a8,#e8a93b)", "avatar_text_color": "#5c3a08",
            "phone_masked": "+234 806 ••• 28", "time_label": "12:34 PM",
            "bank": "OPay", "amount_naira": "15,000", "amount_short": "₦15k",
            "from_name_caps": "CHIAMAKA O. OKEKE", "to_name_caps": "GLOW STUDIO LAGOS",
            "ref": "Hair + manicure Sat 2:30pm", "datetime_label": "24 May 2026 · 12:33:51",
            "biz_name": "Glow Studio Lagos",
            "match_line": "booking #GS-3217 · Chiamaka Okeke · Sat 2:30pm · Tola · hair + manicure",
            "draft_reply": "Hey Chiamaka 🙌 ₦15k deposit received — Saturday 2:30pm with Tola is locked. We'll ping you the morning of with the studio address + parking note. ✨",
        },
        "brief": {
            "day_label": "FRIDAY · 7:02 AM",
            "headline": "14 bookings held · 7 drafts ready · 3 🔥 need your tap",
            "money_label": "💰 ₦15k deposit confirmed",
            "money_detail": "Chiamaka Okeke · OPay · matched to Saturday slot",
            "hot_lines": [
                "Adaeze N. · bridal trial Sunday, asking for package",
                "Funmi A. · monthly facial sub, December slot request",
            ],
            "leak_alert": "Birthday glam enquiry · 2 days no response. Tola free Saturday morning.",
            "slowest_reply": "5 min (vs 4 hrs before ReachNG)",
        },
    },
}


# ─── Custom-vertical trade → closest pack keyword routing ────────────────────
# When a visitor on the cover picks 'Something else' and types their trade,
# we route to the closest existing SCENE_PACK so they still see relevant copy.
_TRADE_KEYWORDS = {
    "hospitality": (
        "restaurant", "bar", "club", "venue", "lounge", "cafe", "hotel",
        "kitchen", "rooftop", "bistro", "eatery", "buka", "shawarma", "pub",
        "catering",
    ),
    "real_estate": (
        "real estate", "property", "properties", "estate", "agent", "agency",
        "broker", "developer", "shortlet", "short-let", "rental", "rentals",
        "letting", "buildings", "homes",
    ),
    "professional_services": (
        "law", "legal", "lawyer", "solicitor", "advisor", "advisory",
        "consult", "consulting", "consultancy", "audit", "accountant",
        "accounting", "tax", "compliance", "chartered", "firm",
    ),
    "education": (
        "school", "schools", "college", "academy", "tutor", "tutoring",
        "creche", "creche", "kindergarten", "lessons", "lesson", "training",
        "education", "educational",
    ),
    "small_business": (
        "salon", "spa", "wellness", "barber", "gym", "fitness",
        "beauty", "studio", "clinic", "boutique", "store", "shop", "atelier",
        "mua", "stylist", "nails",
    ),
}


def _map_trade_to_slug(trade: str) -> str:
    """Closest scene-pack for a typed trade. Default = small_business (safest
    generic SME default)."""
    t = (trade or "").lower().strip()
    if not t:
        return "small_business"
    for slug, words in _TRADE_KEYWORDS.items():
        if any(w in t for w in words):
            return slug
    return "small_business"


def _pick_scene(request: Request) -> dict:
    """Read the personalization cookie set by /set-vertical/{slug}.
    Returns the matching scene pack, falls back to hospitality if missing/unknown.

    For custom (typed) verticals, overlays the typed business name + trade onto
    the closest matching scene-pack so the landing reads as theirs.

    Wave 2: merges the per-vertical 'Three Jobs' scenes (tone / receipt / brief)
    into the returned pack so the mid-page mocks flip with the cookie too."""
    v = (request.cookies.get("reachng_vertical") or "").lower().strip()
    base = SCENE_PACKS.get(v, SCENE_PACKS["hospitality"])
    # Overlay Wave 2 scenes — sensible per-vertical fallback to hospitality
    wave2 = WAVE2_SCENES.get(v, WAVE2_SCENES["hospitality"])
    base = {**base, "tone": wave2["tone"], "receipt": wave2["receipt"], "brief": wave2["brief"]}

    custom_biz   = (request.cookies.get("reachng_biz_name") or "").strip()[:80]
    custom_trade = (request.cookies.get("reachng_biz_trade") or "").strip()[:60]
    if not (custom_biz or custom_trade):
        return base

    # Shallow copy so we don't mutate the module-level pack
    s = dict(base)
    if custom_biz:
        s["biz_name"]  = custom_biz
        # If we're substituting a real biz name, rebuild the draft text generically
        # (avoid 'Hey Funke ... at Altitude Lagos' with a different biz name).
        s["draft_text"] = (
            f"Thanks for reaching out! I've got your message — let me confirm "
            f"availability and ping you right back with options + payment details.\n\n"
            f"— the team at {custom_biz}"
        )
    if custom_trade:
        # Override the displayed label so the 'Showing for' strip says their trade
        s["label"]       = custom_trade
        s["label_emoji"] = f"✨ {custom_trade}"
    s["is_custom"] = True
    return s


# User-Agent fragments belonging to crawlers/social previewers that must NEVER
# be redirected to /start (we need them to index /). Cheap substring check —
# all checks lowercased.
_BOT_UA_FRAGMENTS = (
    "googlebot", "bingbot", "duckduckbot", "yandex", "baiduspider",
    "slurp", "applebot", "facebookexternalhit", "facebot",
    "twitterbot", "linkedinbot", "whatsapp", "telegrambot", "slackbot",
    "discordbot", "embedly", "pinterest", "redditbot",
    "semrushbot", "ahrefsbot", "mj12bot", "dotbot",
    "lighthouse", "headlesschrome",
)


def _looks_like_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return any(f in ua for f in _BOT_UA_FRAGMENTS)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" not in accept:
        return Response(
            content='{"service":"ReachNG","status":"running","docs":"/docs","health":"/health"}',
            media_type="application/json",
        )

    # Personalised-arrival check — a recipient who tapped /hi/{slug} has a
    # `reachng_prospect` cookie set. They jump straight to the landing,
    # bypass the cover, and the template gets their profile for personalisation.
    prospect_profile = _read_prospect_cookie(request)

    # Cover-first routing — first-time human visitors get sent to /start.
    # Exemptions (no redirect, render landing directly):
    #   - cookie reachng_vertical is set (returning visitor or already picked)
    #   - cookie reachng_prospect is set (came in via personalised /hi link)
    #   - any crawler / social previewer user-agent (SEO + link unfurl integrity)
    #   - explicit opt-out via ?skip_cover=1 (used by the Skip link on /start)
    #   - any UTM-tracked arrival (paid traffic, partner links — they get the
    #     landing they were promised, no surprise cover)
    has_cookie     = bool(request.cookies.get("reachng_vertical"))
    has_prospect   = bool(prospect_profile)
    is_bot         = _looks_like_bot(request.headers.get("user-agent", ""))
    skip_cover     = request.query_params.get("skip_cover") in ("1", "true", "yes")
    has_utm        = any(
        request.query_params.get(k) for k in ("utm_source", "utm_medium", "utm_campaign")
    )
    if not (has_cookie or has_prospect or is_bot or skip_cover or has_utm):
        return RedirectResponse(url="/start", status_code=302)

    # If the prospect cookie names a vertical, override the scene with theirs.
    if prospect_profile and prospect_profile.get("vertical"):
        scene = _pick_scene_for_slug(prospect_profile["vertical"]) or _pick_scene(request)
    else:
        scene = _pick_scene(request)

    track_page_viewed(
        page="landing", path="/",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_medium=request.query_params.get("utm_medium"),
        utm_campaign=request.query_params.get("utm_campaign"),
        user_agent=request.headers.get("user-agent", ""),
    )
    return _templates(request).TemplateResponse(
        request, "marketing/landing.html",
        {
            "scene": scene,
            "active_vertical": scene.get("label", "Restaurants & venues"),
            "active_vertical_slug": scene.get("slug", "hospitality"),
            "active_vertical_label": scene.get("label_emoji", "🍽 Restaurants & venues"),
            "prospect": prospect_profile,
        },
    )


def _read_prospect_cookie(request: Request) -> Optional[dict]:
    """Safely parse the reachng_prospect cookie. Returns None on any error."""
    raw = request.cookies.get("reachng_prospect")
    if not raw:
        return None
    try:
        import json as _json
        data = _json.loads(raw)
        if not isinstance(data, dict):
            return None
        # Whitelist + clip
        out = {}
        for k in ("business_name", "contact_name", "first_name", "vertical",
                  "category", "slug"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:200]
        return out or None
    except Exception:
        return None


def _pick_scene_for_slug(slug: str) -> Optional[dict]:
    """Return the scene pack matching a vertical slug, or None."""
    if not slug:
        return None
    return SCENE_PACKS.get(slug.lower().strip())


@router.get("/start", response_class=HTMLResponse, include_in_schema=False)
async def cover(request: Request):
    """Magazine-style personalization cover. Visitor picks a vertical, gets routed
    to the landing with their scene-pack already loaded."""
    track_page_viewed(
        page="cover", path="/start",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_medium=request.query_params.get("utm_medium"),
        utm_campaign=request.query_params.get("utm_campaign"),
    )
    return _templates(request).TemplateResponse(
        request, "marketing/cover.html",
        {"scenes": SCENE_PACKS},
    )


@router.get("/set-vertical/{slug}", include_in_schema=False)
async def set_vertical(slug: str, request: Request):
    """Persist the picked vertical as a cookie + route to landing.
    Unknown slug falls back to hospitality (matches the landing default).
    Also clears any prior custom biz_name/trade overlays — the visitor
    explicitly switched to a canonical vertical, so we drop the custom layer."""
    slug = (slug or "").lower().strip()
    if slug not in SCENE_PACKS:
        slug = "hospitality"
    target = request.query_params.get("next") or "/"
    if not target.startswith("/"):
        target = "/"
    resp = RedirectResponse(url=target, status_code=302)
    resp.set_cookie(
        key="reachng_vertical", value=slug,
        max_age=60 * 60 * 24 * 90,  # 90 days
        samesite="lax", httponly=False, path="/",
    )
    # Clear any stale custom overlays from a prior 'Something else' pick.
    resp.delete_cookie(key="reachng_biz_name",  path="/")
    resp.delete_cookie(key="reachng_biz_trade", path="/")
    return resp


@router.post("/set-vertical-custom", include_in_schema=False)
async def set_vertical_custom(request: Request):
    """Single endpoint for both flows on the cover:

      (a) Canonical pick (cards 01-05): visitor picks one of the 5 known
          verticals + optionally types their business name. Hidden 'slug'
          field carries the vertical; trade is empty.

      (b) Custom pick (card 06 'Something else'): no slug, but biz_name +
          trade are typed. We keyword-map the trade to the closest existing
          SCENE_PACK so the landing still reads as theirs.
    """
    form     = await request.form()
    biz_name = (form.get("biz_name") or "").strip()[:80]
    trade    = (form.get("trade") or "").strip()[:60]
    slug     = (form.get("slug") or "").strip().lower()

    if slug in SCENE_PACKS:
        # (a) canonical pick — visitor optionally typed their biz name
        use_slug      = slug
        cookie_trade  = ""      # don't store a trade label for canonical picks
    elif trade:
        # (b) 'something else' — typed trade, map to closest pack
        use_slug      = _map_trade_to_slug(trade)
        cookie_trade  = trade
    else:
        # No slug, no trade — nothing to do, bounce back to the cover
        return RedirectResponse(url="/start", status_code=302)

    resp = RedirectResponse(url="/?skip_cover=1", status_code=302)
    resp.set_cookie(
        key="reachng_vertical", value=use_slug,
        max_age=60 * 60 * 24 * 90, samesite="lax", httponly=False, path="/",
    )
    if biz_name:
        resp.set_cookie(
            key="reachng_biz_name", value=biz_name,
            max_age=60 * 60 * 24 * 90, samesite="lax", httponly=False, path="/",
        )
    else:
        resp.delete_cookie(key="reachng_biz_name", path="/")
    if cookie_trade:
        resp.set_cookie(
            key="reachng_biz_trade", value=cookie_trade,
            max_age=60 * 60 * 24 * 90, samesite="lax", httponly=False, path="/",
        )
    else:
        resp.delete_cookie(key="reachng_biz_trade", path="/")
    return resp


@router.get("/how-it-works", response_class=HTMLResponse, include_in_schema=False)
async def how_it_works(request: Request):
    track_page_viewed(page="how_it_works", path="/how-it-works",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/how_it_works.html")


@router.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
async def pricing(request: Request):
    track_page_viewed(page="pricing", path="/pricing",
                      referrer=request.headers.get("referer", ""),
                      utm_source=request.query_params.get("utm_source"))
    return _templates(request).TemplateResponse(request, "marketing/pricing.html")


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about(request: Request):
    track_page_viewed(page="about", path="/about",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/about.html")


@router.get("/contact", response_class=HTMLResponse, include_in_schema=False)
async def contact(request: Request):
    track_page_viewed(page="contact", path="/contact",
                      referrer=request.headers.get("referer", ""))
    return _templates(request).TemplateResponse(request, "marketing/contact.html")


@router.get("/hi/{slug}", include_in_schema=False)
async def outreach_personal_link(slug: str):
    """Personalised short link for cold-outreach emails.

    `www.reachng.ng/hi/k3m` — the slug carries this recipient's profile
    (business name, contact name, vertical). On click we set a signed
    cookie `reachng_prospect` and 302 to the landing. The landing template
    reads the cookie and personalises everything: hero banner, vertical
    pre-select, form pre-fills.

    Unknown slug -> 302 to '/' anyway so the click is still useful.
    """
    import json as _json
    target = "/"
    cookie_value: Optional[str] = None
    try:
        from services.outreach_links import resolve_full
        doc = resolve_full(slug) or {}
        target = doc.get("target_url") or "/"
        profile = doc.get("prospect_profile") or {}
        if profile:
            cookie_payload = {
                "business_name": (profile.get("business_name") or "")[:120],
                "contact_name":  (profile.get("contact_name")  or "")[:120],
                "first_name":    (profile.get("first_name")    or "")[:60],
                "vertical":      (profile.get("vertical")      or "")[:32],
                "category":      (profile.get("category")      or "")[:80],
                "slug":          slug,
            }
            cookie_value = _json.dumps(cookie_payload, separators=(",", ":"))
    except Exception as e:
        log.warning("outreach_link_resolve_failed", slug=slug, error=str(e))

    resp = RedirectResponse(url=target, status_code=302)
    if cookie_value:
        resp.set_cookie(
            key="reachng_prospect",
            value=cookie_value,
            max_age=24 * 3600,          # 24h
            httponly=False,             # JS reads it on the landing
            samesite="lax",
            secure=True,
        )
    return resp


# Legacy /o/{slug} alias — older emails already pointed here. Forward to /hi.
@router.get("/o/{slug}", include_in_schema=False)
async def outreach_short_link_legacy(slug: str):
    return RedirectResponse(url=f"/hi/{slug}", status_code=302)


@router.get("/for/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def vertical_lander(slug: str, request: Request):
    content = get_vertical_content(slug)
    if not content:
        return RedirectResponse(url="/", status_code=302)
    track_vertical_lander(
        vertical=slug, path=f"/for/{slug}",
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_campaign=request.query_params.get("utm_campaign"),
    )
    return _templates(request).TemplateResponse(request, "marketing/vertical.html", {**content})


class ContactSubmission(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=4, max_length=40)
    vertical: str = Field(min_length=1, max_length=80)
    message: Optional[str] = Field(default="", max_length=4000)


@router.post("/api/v1/contact", include_in_schema=False)
async def contact_submit(payload: ContactSubmission):
    db = get_db()
    db["contact_submissions"].insert_one({
        "name": payload.name.strip(),
        "business": payload.business.strip(),
        "phone": payload.phone.strip(),
        "vertical": payload.vertical.strip().lower(),
        "message": (payload.message or "").strip(),
        "received_at": datetime.now(timezone.utc),
        "handled": False,
    })
    log.info("contact_submission_received", business=payload.business, vertical=payload.vertical)
    track_contact_submitted(vertical=payload.vertical.strip().lower(),
                            has_message=bool(payload.message))
    return {"ok": True, "message": "Got it. We'll be in touch within 30 minutes during Lagos business hours."}


@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def signup_page(request: Request, plan: Optional[str] = None):
    selected = (plan or "growth").lower()
    track_signup_page(
        selected_plan=selected,
        referrer=request.headers.get("referer", ""),
        utm_source=request.query_params.get("utm_source"),
        utm_campaign=request.query_params.get("utm_campaign"),
    )
    return _templates(request).TemplateResponse(request, "marketing/signup.html", {
        "selected_plan": selected,
        "plans": _live_pricing(),
    })


@router.get("/signup/success", response_class=HTMLResponse, include_in_schema=False)
async def signup_success(request: Request, reference: Optional[str] = None):
    track_page_viewed(page="signup_success", path="/signup/success",
                      referrer=request.headers.get("referer", ""),
                      has_reference=bool(reference))
    portal_path = None
    business = None
    error = None
    if reference:
        try:
            settings = get_settings()
            if not settings.paystack_secret_key:
                error = "Paystack not configured on server."
            else:
                async with httpx.AsyncClient(timeout=15.0) as cli:
                    r = await cli.get(
                        f"{PAYSTACK_BASE}/transaction/verify/{reference}",
                        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
                    )
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    if data.get("status") == "success":
                        signup = get_db()["signups"].find_one({"paystack_reference": reference})
                        if signup and signup.get("portal_token"):
                            portal_path = f"/portal/{signup['portal_token']}"
                            business = signup.get("business_name")
                            track_payment_verified(
                                email=signup.get("owner_email"), reference=reference,
                                plan=signup.get("plan"), vertical=signup.get("vertical"),
                                amount_ngn=signup.get("amount_ngn"), annual=signup.get("annual"),
                                portal_provisioned=True,
                            )
                        else:
                            error = "Payment confirmed. Provisioning your portal - check your WhatsApp + email in 60 seconds."
                            track_payment_verified(
                                email=None, reference=reference,
                                plan=None, vertical=None, amount_ngn=None, annual=None,
                                portal_provisioned=False, state="pending_webhook",
                            )
                    else:
                        error = f"Payment status: {data.get('status', 'unknown')}. Contact us if this is wrong."
                else:
                    error = "Could not verify payment with Paystack."
        except Exception as exc:
            log.error("signup_verify_failed", error=str(exc), reference=reference)
            error = "Verification failed. Don't worry - if you paid, we'll provision you within 5 minutes."
    return _templates(request).TemplateResponse(request, "marketing/signup_success.html", {
        "portal_path": portal_path, "business": business,
        "error": error, "reference": reference,
    })


SUPPORTED_SIGNUP_VERTICALS = {
    "hospitality", "real_estate", "education", "professional_services",
    "small_business", "fitness", "events", "auto", "cooperatives",
    "legal", "insurance", "recruitment", "general",
}


class SignupPayload(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    vertical: str = Field(min_length=1, max_length=80)
    owner_name: str = Field(min_length=1, max_length=200)
    owner_phone: str = Field(min_length=4, max_length=40)
    owner_email: str = Field(min_length=4, max_length=200)
    plan: Literal["starter", "growth", "scale"] = "growth"
    annual: bool = False


@router.post("/api/v1/signup")
async def signup_initialize(payload: SignupPayload, request: Request):
    settings = get_settings()
    if not settings.paystack_secret_key:
        track_signup_failed(stage="config", reason="paystack_not_configured",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=payload.vertical.strip().lower(), status_code=503)
        raise HTTPException(503, "Payments not configured. Email hello@reachng.ng to sign up directly.")
    vertical = payload.vertical.strip().lower()
    if vertical not in SUPPORTED_SIGNUP_VERTICALS:
        track_signup_failed(stage="validation", reason="unsupported_vertical",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=vertical, status_code=400)
        raise HTTPException(400, f"Vertical '{payload.vertical}' not supported.")
    plan_info = _live_pricing()[payload.plan]
    base_ngn = plan_info["ngn"]
    if payload.annual:
        amount_ngn = int(base_ngn * 12 * 0.85)
        plan_label = f"{plan_info['label']} (Annual - 15% off)"
    else:
        amount_ngn = base_ngn
        plan_label = f"{plan_info['label']} (Monthly)"
    reference = f"RNG-SU-{uuid.uuid4().hex[:10].upper()}"
    base_url = str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/signup/success?reference={reference}"
    body = {
        "email": payload.owner_email, "amount": amount_ngn * 100,
        "reference": reference, "currency": "NGN",
        "callback_url": callback_url,
        "metadata": {
            "kind": "signup", "business_name": payload.business_name,
            "vertical": vertical, "owner_name": payload.owner_name,
            "owner_phone": payload.owner_phone, "plan": payload.plan,
            "plan_label": plan_label, "annual": payload.annual, "amount_ngn": amount_ngn,
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(
            f"{PAYSTACK_BASE}/transaction/initialize", json=body,
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}",
                     "Content-Type": "application/json"},
        )
    if r.status_code != 200 or not r.json().get("status"):
        log.error("paystack_init_failed", status=r.status_code, body=r.text[:500])
        track_signup_failed(stage="paystack_init", reason="paystack_rejected",
                            email=payload.owner_email, plan=payload.plan,
                            vertical=vertical, reference=reference, status_code=r.status_code)
        raise HTTPException(502, "Could not initialise payment. Try again or email hello@reachng.ng.")
    data = r.json()["data"]
    get_db()["signups"].insert_one({
        "paystack_reference": reference, "business_name": payload.business_name,
        "vertical": vertical, "owner_name": payload.owner_name,
        "owner_phone": payload.owner_phone, "owner_email": payload.owner_email,
        "plan": payload.plan, "plan_label": plan_label, "amount_ngn": amount_ngn,
        "annual": payload.annual, "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    log.info("signup_initialised", business=payload.business_name,
             plan=payload.plan, reference=reference)
    track_signup_initiated(
        email=payload.owner_email, plan=payload.plan, plan_label=plan_label,
        vertical=vertical, amount_ngn=amount_ngn, annual=payload.annual, reference=reference,
    )
    return {"authorization_url": data["authorization_url"], "reference": reference}


@router.post("/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(request: Request):
    settings = get_settings()
    secret = settings.paystack_secret_key
    if not secret:
        raise HTTPException(503, "Paystack not configured")
    body_bytes = await request.body()
    sig_header = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(sig_header, expected):
        log.warning("paystack_webhook_bad_signature")
        track_paystack_webhook_ignored(reason="bad_signature")
        raise HTTPException(401, "Invalid signature")
    payload = (await request.json()) if body_bytes else {}
    event = payload.get("event")
    data = payload.get("data", {})
    if event != "charge.success":
        track_paystack_webhook_ignored(reason="non_charge_success", event=event,
                                         reference=data.get("reference"))
        return {"ok": True, "ignored": event}
    metadata = data.get("metadata") or {}
    if metadata.get("kind") != "signup":
        track_paystack_webhook_ignored(reason="non_signup", event=event,
                                         reference=data.get("reference"))
        return {"ok": True, "ignored": "non-signup"}
    reference = data.get("reference")
    db = get_db()
    signup = db["signups"].find_one({"paystack_reference": reference})
    if not signup:
        log.warning("paystack_signup_not_found", reference=reference)
        track_paystack_webhook_ignored(reason="no_pending_signup", event=event,
                                         reference=reference)
        return {"ok": True, "ignored": "no-pending-signup"}
    if signup.get("status") == "provisioned":
        track_paystack_webhook_ignored(reason="already_provisioned", event=event,
                                         reference=reference)
        return {"ok": True, "ignored": "already-provisioned"}
    portal_token = pysecrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    paid_until = now + (timedelta(days=365) if signup.get("annual") else timedelta(days=30))
    clients = db["clients"]
    existing = clients.find_one({"name": signup["business_name"]})
    client_doc = {
        "name": signup["business_name"], "vertical": signup["vertical"],
        "brief": "", "active": True, "plan": signup["plan"],
        "payment_status": "paid",
        "monthly_fee_ngn": _live_pricing().get(signup["plan"], {}).get("ngn"),
        "paid_until": paid_until, "owner_name": signup["owner_name"],
        "owner_phone": signup["owner_phone"], "owner_email": signup["owner_email"],
        "agent_name": "EYO", "preferred_channel": "whatsapp",
        "autopilot": False, "signal_listening": False, "holding_message": "",
        "portal_token": portal_token, "portal_created_at": now,
        "onboarded_at": now, "updated_at": now,
    }
    if existing:
        portal_token = existing.get("portal_token") or portal_token
        client_doc["portal_token"] = portal_token
        client_doc.pop("portal_created_at", None)
        clients.update_one({"_id": existing["_id"]}, {"$set": client_doc})
    else:
        clients.insert_one(client_doc)
    db["signups"].update_one(
        {"_id": signup["_id"]},
        {"$set": {"status": "provisioned", "portal_token": portal_token,
                  "provisioned_at": now}},
    )
    log.info("client_provisioned_from_signup", business=signup["business_name"],
             plan=signup["plan"], reference=reference)
    track_client_provisioned(
        email=signup.get("owner_email"), reference=reference,
        plan=signup["plan"], vertical=signup["vertical"],
        business_name=signup["business_name"],
        amount_ngn=signup.get("amount_ngn"), annual=signup.get("annual"),
    )
    # Portal URL — prefer configured app_base_url over request.base_url so
    # links work even when the webhook arrives via the Railway internal host.
    base = (settings.app_base_url or str(request.base_url)).rstrip("/")
    portal_url = f"{base}/portal/{portal_token}"
    owner_name = signup.get("owner_name", "there")
    plan_label = signup.get("plan_label", "subscription")
    paid_until_str = paid_until.strftime("%d %b %Y")

    # 1) WhatsApp welcome — best-effort. Only fires if a WhatsApp connector
    #    (Meta Cloud API or Unipile) is configured; otherwise silently skipped.
    try:
        from tools.outreach import send_whatsapp_for_client
        wa_msg = (
            f"Welcome to ReachNG, {owner_name}!\n\n"
            f"Your {plan_label} is active until {paid_until_str}.\n\n"
            f"Your portal: {portal_url}\n\nNext step: open the portal, fill your Business Brief (5 mins), "
            f"and we'll set up your WhatsApp pairing on a quick call. "
            f"Reply here when you're ready and we'll send the pairing link."
        )
        await send_whatsapp_for_client(phone=signup["owner_phone"], message=wa_msg)
    except Exception as exc:
        log.warning("signup_welcome_whatsapp_failed", error=str(exc), business=signup["business_name"])

    # 2) Email welcome via Resend (hello@reachng.ng) — independent of WhatsApp
    #    so the customer always gets the portal link even before pairing.
    try:
        from tools.outreach import send_email
        owner_email = signup.get("owner_email")
        if owner_email:
            subject = f"Welcome to ReachNG — your portal is ready, {owner_name}"
            text = (
                f"Hi {owner_name},\n\n"
                f"Your ReachNG {plan_label} is now active until {paid_until_str}.\n\n"
                f"Open your portal: {portal_url}\n\n"
                f"Next step: log into the portal and fill your Business Brief (5 minutes). "
                f"Once that's in, we'll send a WhatsApp pairing link so EYO can start drafting "
                f"replies in your voice.\n\n"
                f"Anything urgent — reply to this email or WhatsApp +234 816 458 3657.\n\n"
                f"— EYO from ReachNG\nhello@reachng.ng\n"
            )
            html = f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f8f4ec;color:#14110d;margin:0;padding:32px 16px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8ddc8;border-radius:14px;padding:32px;">
    <div style="font-size:11px;letter-spacing:0.18em;color:#ff5500;text-transform:uppercase;font-weight:700;margin-bottom:18px;">Welcome to ReachNG</div>
    <h1 style="font-family:Georgia,serif;font-size:26px;font-weight:600;letter-spacing:-0.5px;margin:0 0 18px;">Your portal is ready, {owner_name}.</h1>
    <p style="font-size:15px;line-height:1.65;color:#3a342b;margin:0 0 22px;">Your <strong>{plan_label}</strong> is active until <strong>{paid_until_str}</strong>.</p>
    <p style="margin:0 0 28px;">
      <a href="{portal_url}" style="display:inline-block;background:#14110d;color:#fff;text-decoration:none;padding:14px 22px;border-radius:8px;font-size:14px;font-weight:600;">Open your portal →</a>
    </p>
    <p style="font-size:14px;line-height:1.7;color:#3a342b;margin:0 0 18px;"><strong>Next step:</strong> log into the portal and fill your Business Brief (5 minutes). Once that's in, we'll send a WhatsApp pairing link so EYO can start drafting replies in your voice.</p>
    <p style="font-size:13px;line-height:1.7;color:#6b6356;margin:24px 0 0;border-top:1px solid #eee3cf;padding-top:18px;">Anything urgent — reply to this email or WhatsApp <a href="https://wa.me/2348164583657" style="color:#ff5500;text-decoration:none;">+234 816 458 3657</a>.</p>
    <p style="font-size:12px;color:#9b917f;margin:18px 0 0;">— EYO from ReachNG · hello@reachng.ng</p>
  </div>
</body></html>"""
            await send_email(
                to_email=owner_email, subject=subject, body=text, html=html,
                force_smtp=True,  # routes via Resend from hello@reachng.ng
            )
            log.info("signup_welcome_email_sent", business=signup["business_name"], email=owner_email)
    except Exception as exc:
        log.warning("signup_welcome_email_failed", error=str(exc), business=signup["business_name"])

    # 3) Branded subscription receipt via Resend (separate from the Paystack auto-receipt).
    #    Built into services/subscription_invoice.py; this is the wire-up so it actually fires.
    try:
        from services.subscription_invoice import generate_receipt, email_receipt
        receipt = generate_receipt(signup=signup, client_id=str(existing["_id"]) if existing else None, paid_at=now)
        await email_receipt(receipt)
        log.info("subscription_receipt_dispatched",
                 receipt_no=receipt.get("receipt_number"),
                 business=signup["business_name"])
    except Exception as exc:
        log.warning("subscription_receipt_failed", error=str(exc), business=signup["business_name"])

    return {"ok": True, "provisioned": True, "portal_token": portal_token}


# Public founder-slots counter — drives the live scarcity strip on /pricing.
# Visible-scarcity converts better than abstract "first 50" phrasing.
FOUNDER_CAP = 50
_SLOTS_CACHE: dict = {"taken": None, "expires_at": None}

@router.get("/api/v1/founder-slots", include_in_schema=False)
async def founder_slots():
    """Returns {cap, taken, remaining} based on count of active paying clients.
    Cached 5 minutes so a viral spike doesn't hammer Mongo."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    cached_until = _SLOTS_CACHE.get("expires_at")
    if cached_until and now < cached_until and _SLOTS_CACHE.get("taken") is not None:
        taken = _SLOTS_CACHE["taken"]
    else:
        try:
            taken = get_db()["clients"].count_documents({"active": True, "payment_status": "paid"})
        except Exception:
            taken = 0
        _SLOTS_CACHE["taken"] = taken
        _SLOTS_CACHE["expires_at"] = now + timedelta(minutes=5)
    return {
        "cap":       FOUNDER_CAP,
        "taken":     taken,
        "remaining": max(0, FOUNDER_CAP - taken),
        "sold_out":  taken >= FOUNDER_CAP,
    }


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt(request: Request):
    base = str(request.base_url).rstrip("/")
    return f"""User-agent: *
Allow: /
Allow: /portal/demo
Disallow: /dashboard
Disallow: /admin
Disallow: /api/
Disallow: /webhooks
Disallow: /portal/data/
Disallow: /docs
Disallow: /openapi.json
Disallow: /mcp
Sitemap: {base}/sitemap.xml
"""


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request):
    base = str(request.base_url).rstrip("/")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pages = [
        ("/", "1.0", "weekly"), ("/how-it-works", "0.9", "monthly"),
        ("/pricing", "0.9", "monthly"), ("/signup", "0.95", "monthly"),
        ("/about", "0.7", "monthly"), ("/contact", "0.8", "monthly"),
        ("/portal/demo", "0.8", "weekly"),
    ]
    for slug in list_canonical_slugs():
        pages.append((f"/for/{slug}", "0.85", "monthly"))
    for vertical in ["hospitality", "real_estate", "education", "professional_services", "small_business"]:
        pages.append((f"/portal/demo/{vertical}", "0.7", "weekly"))
    urls = []
    for path, priority, freq in pages:
        urls.append(
            f"  <url>\n    <loc>{base}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
