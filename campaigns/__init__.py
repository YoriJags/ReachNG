from .real_estate import RealEstateCampaign
from .recruitment import RecruitmentCampaign
from .events import EventsCampaign
from .fintech import FintechCampaign
from .legal import LegalCampaign
from .logistics import LogisticsCampaign
from .agriculture import AgricultureCampaign
from .agency_sales import AgencySalesCampaign
from .small_business import SmallBusinessCampaign
from .b2b_saas import B2BSaaSCampaign

CAMPAIGN_REGISTRY = {
    "real_estate":   RealEstateCampaign,
    "recruitment":   RecruitmentCampaign,
    "events":        EventsCampaign,
    "fintech":       FintechCampaign,
    "legal":         LegalCampaign,
    "logistics":     LogisticsCampaign,
    "agriculture":   AgricultureCampaign,
    "agency_sales":  AgencySalesCampaign,
    "small_business": SmallBusinessCampaign,
    "b2b_saas":      B2BSaaSCampaign,
}

__all__ = [
    "RealEstateCampaign", "RecruitmentCampaign", "EventsCampaign",
    "FintechCampaign", "LegalCampaign", "LogisticsCampaign", "AgricultureCampaign",
    "AgencySalesCampaign", "SmallBusinessCampaign", "B2BSaaSCampaign",
    "CAMPAIGN_REGISTRY",
]
