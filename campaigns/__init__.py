from .real_estate import RealEstateCampaign
from .recruitment import RecruitmentCampaign
from .events import EventsCampaign
from .fintech import FintechCampaign
from .legal import LegalCampaign
from .logistics import LogisticsCampaign

CAMPAIGN_REGISTRY = {
    "real_estate": RealEstateCampaign,
    "recruitment": RecruitmentCampaign,
    "events": EventsCampaign,
    "fintech": FintechCampaign,
    "legal": LegalCampaign,
    "logistics": LogisticsCampaign,
}

__all__ = [
    "RealEstateCampaign", "RecruitmentCampaign", "EventsCampaign",
    "FintechCampaign", "LegalCampaign", "LogisticsCampaign",
    "CAMPAIGN_REGISTRY",
]
