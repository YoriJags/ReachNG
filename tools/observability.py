"""
Observability — Sentry error tracking, PII-scrubbed.

No-op until SENTRY_DSN is set, so dev + tests never phone home and the import
graph never hard-depends on sentry-sdk being installed.

CLAUDE.md rule: never ship customer PII off-box. Sentry's send_default_pii is
left False AND a before_send hook redacts phone/email patterns from event
messages, exception values, and request data as a belt-and-braces second layer.
"""
from __future__ import annotations

import re

import structlog

from config import get_settings

log = structlog.get_logger()

# Nigerian phone (+234… / 0…) and any email.
_PHONE = re.compile(r"(?:\+?234|0)\d{9,10}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

_sentry_on = False


def _scrub(s):
    if not isinstance(s, str):
        return s
    s = _PHONE.sub("[phone]", s)
    s = _EMAIL.sub("[email]", s)
    return s


def _before_send(event, hint):
    """Redact PII and drop request payloads that could carry it."""
    try:
        le = event.get("logentry")
        if isinstance(le, dict) and le.get("message"):
            le["message"] = _scrub(le["message"])
        for exc in ((event.get("exception") or {}).get("values") or []):
            if exc.get("value"):
                exc["value"] = _scrub(exc["value"])
        req = event.get("request")
        if isinstance(req, dict):
            req.pop("data", None)            # request body — may hold phone/email
            req.pop("cookies", None)
            hdrs = req.get("headers")
            if isinstance(hdrs, dict):
                for h in ("authorization", "cookie", "unipile-auth", "x-hub-signature-256"):
                    hdrs.pop(h, None)
    except Exception:
        pass
    return event


def init_sentry() -> bool:
    """Initialise Sentry if SENTRY_DSN is configured. Safe to call once at boot."""
    global _sentry_on
    settings = get_settings()
    dsn = getattr(settings, "sentry_dsn", None)
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=getattr(settings, "app_env", "development"),
            traces_sample_rate=float(getattr(settings, "sentry_traces_sample_rate", 0.0) or 0.0),
            send_default_pii=False,
            before_send=_before_send,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        _sentry_on = True
        log.info("sentry_initialised", env=getattr(settings, "app_env", ""))
        return True
    except Exception as e:
        log.warning("sentry_init_failed", error=str(e))
        return False


def capture_message(message: str, level: str = "warning", **tags) -> None:
    """Send a scrubbed breadcrumb/event to Sentry. No-op when Sentry is off.
    Use for things FastAPI swallows (e.g. webhook signature failures) that we
    still want a tail of."""
    if not _sentry_on:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, str(v))
            sentry_sdk.capture_message(_scrub(message), level=level)
    except Exception:
        pass


def capture_exception(exc: BaseException | None = None, **tags) -> None:
    """Explicitly capture a handled exception (scrubbed). No-op when Sentry off."""
    if not _sentry_on:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, str(v))
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass
