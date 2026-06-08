"""Traction roll-up — aggregates the North-Star numbers from existing collections."""
from __future__ import annotations

import services.traction as traction


class _FakeCol:
    def __init__(self, *, counts=None, agg=None):
        self._counts = counts or []   # list of (matcher_fn, value)
        self._agg = agg or []

    def count_documents(self, query):
        for matcher, val in self._counts:
            if matcher(query):
                return val
        return 0

    def aggregate(self, pipeline):
        return iter(self._agg)


class _FakeDB:
    def __init__(self, cols):
        self._cols = cols

    def __getitem__(self, name):
        return self._cols[name]


def _install(monkeypatch, cols):
    monkeypatch.setattr(traction, "get_db", lambda: _FakeDB(cols))


def test_summary_shapes_and_estimates(monkeypatch):
    clients = _FakeCol(counts=[
        (lambda q: q == {"active": True}, 7),
        (lambda q: q.get("payment_status") == "paid" and q.get("active") is True, 5),
        (lambda q: set(q.keys()) == {"onboarded_at"}, 4),                      # cohort
        (lambda q: "onboarded_at" in q and q.get("active") is True, 3),        # retained
    ])
    outcomes = _FakeCol(counts=[
        (lambda q: q.get("status") == "win", 10),
        (lambda q: q.get("status") == "miss", 5),
    ])
    messages = _FakeCol(
        counts=[
            (lambda q: "status" not in q, 40),                                 # total
            (lambda q: "status" in q, 22),                                     # approved/sent
        ],
        agg=[{"_id": "whatsapp", "count": 30}, {"_id": "email", "count": 10}],
    )
    _install(monkeypatch, {"clients": clients, "outcomes": outcomes, "pending_approvals": messages})

    out = traction.traction_summary(days=30)

    assert out["headline"]["active_clients"] == 7
    assert out["headline"]["messages_handled"] == 40
    # 10 wins × ₦50,000 floor
    assert out["headline"]["est_value_recovered_ngn"] == 500_000
    assert out["clients"]["retention_30d_pct"] == 75.0          # 3 of 4
    assert out["outcomes"]["win_rate_pct"] == round(100 * 10 / 15, 1)
    assert out["messages"]["channel_mix"] == {"whatsapp": 30, "email": 10}


def test_degrades_to_zero_on_db_error(monkeypatch):
    class _Boom:
        def __getitem__(self, name):
            raise RuntimeError("no db")
    monkeypatch.setattr(traction, "get_db", lambda: _Boom())

    out = traction.traction_summary(days=30)
    assert out["headline"]["active_clients"] == 0
    assert out["headline"]["est_value_recovered_ngn"] == 0
    assert out["outcomes"]["win_rate_pct"] is None
