from .real_estate import RealEstateCampaign
from .recruitment import RecruitmentCampaign
from .events import EventsCampaign

CAMPAIGN_REGISTRY = {
    "real_estate": RealEstateCampaign,
    "recruitment": RecruitmentCampaign,
    "events": EventsCampaign,
}

__all__ = ["RealEstateCampaign", "RecruitmentCampaign", "EventsCampaign", "CAMPAIGN_REGISTRY"]
