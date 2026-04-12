from .real_estate import RealEstateCampaign
from .recruitment import RecruitmentCampaign
from .events import EventsCampaign
from .fintech import FintechCampaign
from .legal import LegalCampaign
from .logistics import LogisticsCampaign
from .agriculture import AgricultureCampaign
from .agency_sales import AgencySalesCampaign

CAMPAIGN_REGISTRY = {
    "real_estate": RealEstateCampaign,
    "recruitment": RecruitmentCampaign,
    "events": EventsCampaign,
    "fintech": FintechCampaign,
    "legal": LegalCampaign,
    "logistics": LogisticsCampaign,
    "agriculture": AgricultureCampaign,
    "agency_sales": AgencySalesCampaign,
}

__all__ = [
    "RealEstateCampaign", "RecruitmentCampaign", "EventsCampaign",
    "FintechCampaign", "LegalCampaign", "LogisticsCampaign", "AgricultureCampaign",
    "AgencySalesCampaign", "CAMPAIGN_REGISTRY",
]
