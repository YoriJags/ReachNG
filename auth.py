"""
Basic auth guard for the dashboard and all API routes.
Credentials are set via DASHBOARD_USER and DASHBOARD_PASS env vars.
If not set, auth is disabled (development only — always set in production).
"""
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config import get_settings
import structlog

log = structlog.get_logger()

security = HTTPBasic(auto_error=True)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    settings = get_settings()
    expected_user = getattr(settings, "dashboard_user", None)
    expected_pass = getattr(settings, "dashboard_pass", None)

    # If credentials not configured, skip auth (dev only)
    if not expected_user or not expected_pass:
        log.warning("dashboard_auth_disabled", reason="DASHBOARD_USER/DASHBOARD_PASS not set")
        return "anonymous"

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        expected_user.encode("utf-8"),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        expected_pass.encode("utf-8"),
    )

    if not (user_ok and pass_ok):
        log.warning("dashboard_auth_failed", username=credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm='ReachNG'"},
        )

    return credentials.username
