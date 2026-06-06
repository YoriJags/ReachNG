"""Real-contract tests (no mocks).

The adapters call across modules with specific kwargs. These introspect the
ACTUAL function signatures so a refactor that drops/renames a parameter fails CI,
instead of slipping past mock-heavy unit tests. This is the cheap guard against
the "tests are green but the real contract drifted" risk.
"""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-contracts")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/contracts")


def test_queue_draft_accepts_every_kwarg_callers_pass():
    from tools.hitl import queue_draft
    params = inspect.signature(queue_draft).parameters
    # Union of kwargs used by the email / meta / haggle / referral wirings.
    for kw in ("contact_id", "contact_name", "vertical", "channel", "message",
               "subject", "email", "phone", "client_name", "source",
               "inbound_context"):
        assert kw in params, f"queue_draft() is missing '{kw}' that a caller passes"


def test_draft_inbound_reply_contract():
    from agent.brain import draft_inbound_reply
    params = inspect.signature(draft_inbound_reply).parameters
    for kw in ("inbound_text", "business_name", "vertical", "intent", "channel"):
        assert kw in params


def test_send_whatsapp_for_client_contract():
    from tools.outreach import send_whatsapp_for_client
    params = inspect.signature(send_whatsapp_for_client).parameters
    for kw in ("phone", "message", "client_doc"):
        assert kw in params


def test_send_email_contract():
    from tools.outreach import send_email
    params = inspect.signature(send_email).parameters
    for kw in ("to_email", "subject", "body", "force_smtp"):
        assert kw in params


def test_classify_inbound_exists():
    from services.inbound_classifier import classify_inbound
    assert callable(classify_inbound)
