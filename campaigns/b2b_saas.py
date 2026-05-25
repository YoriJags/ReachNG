"""
ReachNG self-outreach campaign — Client #0 path.

Uses the standard discovery layer (Maps + lean_scraper + email_finder) but
routes message drafting through services.reachng_self_outreach.draft_with_link()
instead of the per-vertical drafter. See campaigns/base.py:380-398 — the
b2b_saas branch fires the founder-voice prompt + UTM-tagged landing link.

Always prefers email (we send from hello@reachng.ng via Resend).
"""
from .base import BaseCampaign


class B2BSaaSCampaign(BaseCampaign):
    vertical = "b2b_saas"
    preferred_channel = "email"
