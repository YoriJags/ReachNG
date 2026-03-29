from .base import BaseCampaign


class LegalCampaign(BaseCampaign):
    vertical = "legal"
    preferred_channel = "email"   # Law firms expect professional email, not WhatsApp cold contact
