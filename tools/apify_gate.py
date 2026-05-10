"""
Vertical gate for Apify spend.

Apify pays back where IG / TikTok signals are the actual lead surface.
For LinkedIn / email-led verticals (legal, fintech, pro services, clinics,
recruitment, insurance, logistics) the spend is wasted — those buyers
don't live on IG.

Single source of truth so every Apify call site stays consistent.
"""
from __future__ import annotations

from config import get_settings


# IG / TikTok-native verticals — Apify scrapers pay back here.
APIFY_VERTICALS: frozenset[str] = frozenset({
    "small_business",
    "hospitality",
    "fitness",
    "events",
    "auto",
    "real_estate",   # Lagos luxury agents are heavily IG-led
    "agriculture",   # farm-to-table buyers post on IG, restaurants browse IG
})


def should_use_apify_for(vertical: str | None) -> bool:
    """
    True only when:
      1. APIFY_API_TOKEN is set, AND
      2. The vertical is in the IG-native list.

    Falls back to False (silent no-op) for everything else.
    """
    if not vertical:
        return False
    settings = get_settings()
    if not settings.apify_api_token:
        return False
    return vertical.strip().lower() in APIFY_VERTICALS
