from .base import BaseCampaign


class SmallBusinessCampaign(BaseCampaign):
    vertical = "small_business"
    preferred_channel = "whatsapp"  # IG/TikTok SMEs live on WhatsApp — no email on file
