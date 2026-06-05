"""Haggle detection — is_haggle / extract_offer / haggle_topic. Pure."""
from __future__ import annotations

import pytest

from services.haggle_detect import is_haggle, extract_offer, haggle_topic


@pytest.mark.parametrize("msg", [
    "what's your last price?",
    "any discount for the 2 bedroom?",
    "abeg reduce small",
    "can you do better?",
    "that's too expensive",
])
def test_haggle_detected(msg):
    assert is_haggle(msg) is True


@pytest.mark.parametrize("msg", [
    "I'll take it",
    "how much for the flat?",     # a plain price ask is not a haggle
    "good morning",
    "",
])
def test_non_haggle_ignored(msg):
    assert is_haggle(msg) is False


def test_extract_offer():
    assert extract_offer("can you do ₦2,000,000?") == 2_000_000
    assert extract_offer("last price?") is None     # vague, no number


def test_haggle_topic():
    assert haggle_topic("₦2m last price for the 2 bedroom") == "2 bedroom"
