"""Unified customer dossier — resolve the other identifier + merge timelines."""
from __future__ import annotations

import services.customer_dossier as cd


class _Cursor(list):
    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self


class _Col:
    def __init__(self, rows):
        self.rows = rows

    def find(self, q, *a, **k):
        out = [r for r in self.rows if r.get("client_name") == q.get("client_name")]
        if "from_email" in q:
            out = [r for r in out if r.get("from_email") == q["from_email"]]
        if "sender_phone" in q:
            rgx = q["sender_phone"]["$regex"]
            out = [r for r in out if rgx in str(r.get("sender_phone", ""))]
        return _Cursor(out)


class _Db:
    def __init__(self, emails, wa):
        self.cols = {"email_messages": _Col(emails), "inbound_messages": _Col(wa)}

    def __getitem__(self, name):
        return self.cols[name]


def test_dossier_merges_both_channels(monkeypatch):
    emails = [{"client_name": "Altitude", "from_email": "tunde@gmail.com",
               "direction": "inbound", "subject": "Duplex", "body": "still available?",
               "received_at": "2026-06-01T09:00:00"}]
    wa = [{"client_name": "Altitude", "sender_phone": "2348031234567",
           "body": "are you around?", "received_at": "2026-06-02T10:00:00"}]
    monkeypatch.setattr(cd, "_db", lambda: _Db(emails, wa))
    # phone given -> identity resolves the linked email
    import services.identity as idn
    monkeypatch.setattr(idn, "linked_email_for_phone", lambda c, p: "tunde@gmail.com")

    d = cd.dossier_for("Altitude", phone="08031234567")
    assert d["phone"] == "2348031234567"
    assert d["email"] == "tunde@gmail.com"
    assert d["linked"] is True
    assert set(d["channels"]) == {"email", "whatsapp"}
    assert len(d["events"]) == 2
    # merged + time-ordered: email (Jun 1) before whatsapp (Jun 2)
    assert d["events"][0]["channel"] == "email"
    assert d["events"][1]["channel"] == "whatsapp"


def test_dossier_email_only_when_no_link(monkeypatch):
    emails = [{"client_name": "Altitude", "from_email": "a@b.com",
               "direction": "inbound", "body": "hi", "received_at": "2026-06-01"}]
    monkeypatch.setattr(cd, "_db", lambda: _Db(emails, []))
    import services.identity as idn
    monkeypatch.setattr(idn, "linked_phone_for_email", lambda c, e: None)

    d = cd.dossier_for("Altitude", email="a@b.com")
    assert d["email"] == "a@b.com" and d["phone"] is None
    assert d["linked"] is False
    assert d["channels"] == ["email"]
