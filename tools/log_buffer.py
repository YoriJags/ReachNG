"""
In-memory circular log buffer — captures structlog output for dashboard display.
Stores last 200 log entries. Exposed via /api/v1/logs/recent.
"""
from collections import deque
from datetime import datetime, timezone
import threading

_BUFFER: deque = deque(maxlen=200)
_LOCK = threading.Lock()

# Log levels to surface (skip noisy debug lines)
_SHOW_LEVELS = {"info", "warning", "error", "critical"}

# Keys to strip from the event dict to keep entries readable
_STRIP_KEYS = {"_record", "exc_info", "stack_info"}


def add_log_entry(event: dict) -> None:
    level = (event.get("level") or "").lower()
    if level not in _SHOW_LEVELS:
        return

    entry = {
        "ts":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level,
        "event": event.get("event", ""),
        "data":  {k: v for k, v in event.items()
                  if k not in ("event", "level", "timestamp") and k not in _STRIP_KEYS},
    }
    with _LOCK:
        _BUFFER.append(entry)


def get_recent(limit: int = 100) -> list[dict]:
    with _LOCK:
        entries = list(_BUFFER)
    return entries[-limit:]


def clear() -> None:
    with _LOCK:
        _BUFFER.clear()


# ── structlog processor ────────────────────────────────────────────────────────

def buffer_processor(logger, method, event_dict: dict) -> dict:
    """structlog processor — captures each log event into the buffer."""
    add_log_entry({"level": method, **event_dict})
    return event_dict
