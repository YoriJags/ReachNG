"""Direct IMAP/SMTP — pure email parsing + safe gating (no network)."""
from __future__ import annotations

import services.email_imap as ei


def test_parse_simple_email():
    raw = (b"From: Tunde <tunde@gmail.com>\r\n"
           b"Subject: Lekki duplex\r\n"
           b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
           b"Is the duplex still available?\r\n")
    p = ei.parse_email_message(raw)
    assert p["from_email"] == "tunde@gmail.com"
    assert p["from_name"] == "Tunde"
    assert p["subject"] == "Lekki duplex"
    assert "still available" in p["body"]


def test_parse_multipart_prefers_plain_text():
    raw = (b"From: a@b.com\r\nSubject: Hi\r\nMIME-Version: 1.0\r\n"
           b'Content-Type: multipart/alternative; boundary="BB"\r\n\r\n'
           b"--BB\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
           b"plain text body here\r\n"
           b"--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
           b"<p>html</p>\r\n--BB--\r\n")
    p = ei.parse_email_message(raw)
    assert p["from_email"] == "a@b.com"
    assert "plain text body here" in p["body"]
    assert "<p>" not in p["body"]


def test_send_without_creds_returns_false():
    # non-imap client -> no creds -> no send, no crash
    assert ei.send_email_via_client({"name": "X"}, to_email="a@b.com",
                                    subject="s", body="b") is False


def test_poll_without_creds_returns_zero():
    assert ei.poll_client_inbox({"name": "X"}) == 0
