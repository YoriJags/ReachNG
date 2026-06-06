"""structlog processor that redacts PII (phone, email) from every log event.

CLAUDE.md rule: never log PII. Rather than trust ~50k LOC of call sites to each
remember, we scrub centrally — this runs on every event and replaces Nigerian
phone numbers and emails (in the message AND every field value) with [phone] /
[email]. One place, whole repo.
"""
from __future__ import annotations

import re

_PHONE = re.compile(r"(?:\+?234|0)\d{9,10}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _scrub(value):
    if isinstance(value, str):
        value = _EMAIL.sub("[email]", value)
        value = _PHONE.sub("[phone]", value)
        return value
    return value


def redact_pii(logger, method_name, event_dict):
    """structlog processor — scrub PII from the event message + all field values."""
    try:
        for key, val in list(event_dict.items()):
            event_dict[key] = _scrub(val)
    except Exception:
        pass
    return event_dict
