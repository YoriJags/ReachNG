"""Email pairing — channel routing helpers (pure). The shared Unipile webhook
uses these to decide WhatsApp vs email."""
from __future__ import annotations

import pytest

from services.email_pairing import (
    parse_channel_from_name, is_email_account_type, EMAIL_PROVIDERS,
)


def test_email_name_routes_to_email():
    assert parse_channel_from_name("client:abc123|chan:email") == "email"


@pytest.mark.parametrize("name", [
    "client:abc123",                  # legacy whatsapp
    "client:abc123|label:primary",    # multi-line whatsapp
    None,
    "",
])
def test_non_email_names_route_to_whatsapp(name):
    assert parse_channel_from_name(name) == "whatsapp"


@pytest.mark.parametrize("t", ["GOOGLE", "outlook", "MAIL", "imap", "Gmail"])
def test_email_account_types_recognised(t):
    assert is_email_account_type(t) is True


@pytest.mark.parametrize("t", ["WHATSAPP", "MESSENGER", "", None])
def test_non_email_account_types(t):
    assert is_email_account_type(t) is False


def test_email_providers_offered():
    assert "GOOGLE" in EMAIL_PROVIDERS and "OUTLOOK" in EMAIL_PROVIDERS
