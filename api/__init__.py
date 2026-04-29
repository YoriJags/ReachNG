from .campaigns import router as campaigns_router
from .contacts import router as contacts_router
from .clients import router as clients_router
from .dashboard import router as dashboard_router
from .data import router as data_router
from .approvals import router as approvals_router, public_router as approvals_public_router
from .roi import router as roi_router
from .social import router as social_router
from .hooks import router as hooks_router
from .portal import router as portal_router
from .ab_testing import router as ab_router
from .referrals import router as referrals_router
from .competitors import router as competitors_router
from .invoices import router as invoices_router
from .b2c import router as b2c_router, public_router as b2c_public_router
from .invoice_chaser import router as invoice_chaser_router
from .school_fees import router as school_fees_router
from .webhooks import router as webhooks_router
from .plans import router as plans_router
from .legal_review import router as legal_review_router
from .loan_officer import router as loan_officer_router
from .debt_collector import router as debt_collector_router
from .market_credit import router as market_credit_router
from .product_auth import router as product_auth_router
from .material_check import router as material_check_router
from .fuel_reprice import router as fuel_reprice_router
from .float_optimizer import router as float_optimizer_router
from .fx_salary import router as fx_salary_router
from .moonlighting import router as moonlighting_router
from .salary_erosion import router as salary_erosion_router
from .fx_lock import router as fx_lock_router
from .hr_suite import router as hr_suite_router
from .estate import router as estate_router
from .portal_estate import router as portal_estate_router
from .portal_talent import router as portal_talent_router
from .closer import router as closer_router, public_router as closer_public_router
from .brief import router as brief_router, public_router as brief_public_router
from .legal import router as legal_router, public_router as legal_public_router

__all__ = [
    "campaigns_router", "contacts_router", "clients_router",
    "dashboard_router", "data_router", "approvals_router",
    "approvals_public_router",
    "roi_router", "social_router", "hooks_router",
    "portal_router", "ab_router", "referrals_router", "competitors_router",
    "invoices_router", "b2c_router", "b2c_public_router", "invoice_chaser_router",
    "school_fees_router", "webhooks_router", "plans_router",
    "legal_review_router", "loan_officer_router",
    "debt_collector_router", "market_credit_router", "product_auth_router",
    "material_check_router", "fuel_reprice_router", "float_optimizer_router",
    "fx_salary_router", "moonlighting_router",
    "salary_erosion_router", "fx_lock_router",
    "hr_suite_router", "estate_router",
    "portal_estate_router", "portal_talent_router",
    "closer_router", "closer_public_router",
    "brief_router", "brief_public_router",
    "legal_router", "legal_public_router",
]
