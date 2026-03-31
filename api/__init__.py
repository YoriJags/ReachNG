from .campaigns import router as campaigns_router
from .contacts import router as contacts_router
from .clients import router as clients_router
from .dashboard import router as dashboard_router
from .data import router as data_router
from .approvals import router as approvals_router
from .roi import router as roi_router
from .social import router as social_router
from .hooks import router as hooks_router
from .portal import router as portal_router
from .ab_testing import router as ab_router
from .referrals import router as referrals_router
from .competitors import router as competitors_router

__all__ = [
    "campaigns_router", "contacts_router", "clients_router",
    "dashboard_router", "data_router", "approvals_router",
    "roi_router", "social_router", "hooks_router",
    "portal_router", "ab_router", "referrals_router", "competitors_router",
]
