from .campaigns import router as campaigns_router
from .contacts import router as contacts_router
from .clients import router as clients_router
from .dashboard import router as dashboard_router
from .data import router as data_router

__all__ = ["campaigns_router", "contacts_router", "clients_router", "dashboard_router", "data_router"]
