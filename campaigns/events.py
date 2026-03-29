from .base import BaseCampaign


class EventsCampaign(BaseCampaign):
    vertical = "events"
    preferred_channel = "whatsapp"  # Event promoters are on WhatsApp
