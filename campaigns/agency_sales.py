from .base import BaseCampaign


class AgencySalesCampaign(BaseCampaign):
    """
    ReachNG self-promotion campaign.
    Discovers high-value Lagos businesses across all sectors and pitches ReachNG's service.
    Run this to find paying clients for ReachNG itself.
    """
    vertical = "agency_sales"
    preferred_channel = "whatsapp"
    multi_channel = True   # Queue both WhatsApp + email drafts when both are available
