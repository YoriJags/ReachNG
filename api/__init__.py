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
from .invoices import router as invoices_router
from .b2c import router as b2c_router
from .invoice_chaser import router as invoice_chaser_router
from .school_fees import router as school_fees_router
from .webhooks import router as webhooks_router
from .plans import router as plans_router
from .legal_review import router as legal_review_router
from .loan_officer import router as loan_officer_router

__all__ = [
    "campaigns_router", "contacts_router", "clients_router",
    "dashboard_router", "data_router", "approvals_router",
    "roi_router", "social_router", "hooks_router",
    "portal_router", "ab_router", "referrals_router", "competitors_router",
    "invoices_router", "b2c_router", "invoice_chaser_router",
    "school_fees_router", "webhooks_router", "plans_router",
    "legal_review_router", "loan_officer_router",
]
