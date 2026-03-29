from .base import BaseCampaign


class RecruitmentCampaign(BaseCampaign):
    vertical = "recruitment"
    preferred_channel = "email"  # HR professionals prefer email for B2B
