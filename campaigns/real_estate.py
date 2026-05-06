from .base import BaseCampaign


class RealEstateCampaign(BaseCampaign):
    vertical = "real_estate"
    preferred_channel = "email"  # First touch via email (formal intro); WhatsApp for follow-up
