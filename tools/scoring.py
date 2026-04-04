"""
Lead scoring — rates each contact 0-100 before we spend API credits on them.
Higher score = better lead = contacted first.
"""
from typing import Optional

# Weights must sum to 100
_W_RATING   = 30   # Google Maps rating quality
_W_PHONE    = 25   # Has WhatsApp-able phone number
_W_WEBSITE  = 20   # Has website (more established biz)
_W_CATEGORY = 15   # Category matches high-value targets
_W_REVIEWS  = 10   # Rating count proxy for establishment

# High-value categories per vertical
HIGH_VALUE_CATEGORIES = {
    "real_estate":  {"real estate agency", "property management company", "real estate developer"},
    "recruitment":  {"employment agency", "human resources consulting", "staffing agency"},
    "events":       {"event management company", "wedding planner", "event venue"},
    "fintech":      {"financial institution", "bank", "investment company"},
    "legal":        {"lawyer", "law firm", "legal services"},
    "logistics":    {"moving company", "freight forwarding", "logistics service"},
    "agriculture":  {"farm", "agribusiness", "food processing company", "agricultural cooperative"},
}


def score_contact(
    vertical: str,
    rating: Optional[float],
    has_phone: bool,
    has_website: bool,
    category: Optional[str],
    outreach_count: int = 0,
) -> int:
    """
    Returns a lead quality score 0-100.
    Penalised by previous failed outreach attempts.
    """
    score = 0.0

    # Rating: 5.0 → 30pts, 0 → 0pts
    if rating:
        score += (rating / 5.0) * _W_RATING

    # Contact channels
    if has_phone:
        score += _W_PHONE
    if has_website:
        score += _W_WEBSITE

    # Category match
    if category:
        targets = HIGH_VALUE_CATEGORIES.get(vertical, set())
        if category.lower() in targets:
            score += _W_CATEGORY
        else:
            score += _W_CATEGORY * 0.4   # partial credit for any category

    # Review count proxy — if we have a rating, assume it has reviews
    if rating and rating >= 4.0:
        score += _W_REVIEWS
    elif rating and rating >= 3.0:
        score += _W_REVIEWS * 0.5

    # Penalty: each prior outreach attempt with no reply reduces score
    score -= outreach_count * 8

    return max(0, min(100, round(score)))
