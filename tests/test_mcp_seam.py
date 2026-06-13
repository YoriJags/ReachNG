"""EYO action layer (MCP seam) — flag gate, tenant-scoped encrypted connections,
and the HITL propose -> approve -> execute path. Pure-logic: an in-memory fake DB
stands in for Mongo, real Fernet for the crypto round-trip.
"""
from __future__ import annotations

import re
import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("cryptography")

import services.crypto as crypto
import services.connections as conns
import services.mcp_actions as actions


# ─── In-memory Mongo stand-in (covers exactly the ops the seam uses) ──────────

def _dotted(doc: dict, path: str):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(doc: dict, flt: dict) -> bool:
    for k, cond in flt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = _dotted(doc, k)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            opts = cond.get("$options", "")
            for op, target in cond.items():
                if op == "$options":
                    continue
                if op == "$regex":
                    flags = re.IGNORECASE if "i" in opts else 0
                    if val is None or not re.search(target, str(val), flags):
                        return False
                elif op == "$ne":
                    if val == target:
                        return False
                elif op == "$gt":
                    if val is None or not val > target:
                        return False
                elif op == "$exists":
                    if (k in doc) != bool(target):
                        return False
                else:
                    return False
        elif val != cond:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: d.get(field) or 0, reverse=(direction == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    def __iter__(self): return iter(self._docs)


class _FakeCol:
    def __init__(self): self.docs = []
    def create_index(self, *a, **k): return None

    def insert_one(self, doc):
        from bson import ObjectId
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    def find_one(self, flt, projection=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    def find(self, flt=None):
        flt = flt or {}
        return _Cursor([dict(d) for d in self.docs if _match(d, flt)])

    def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        if upsert:
            new = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            new.update(update.get("$setOnInsert", {}))
            new.update(update.get("$set", {}))
            self.insert_one(new)
            return SimpleNamespace(matched_count=0)
        return SimpleNamespace(matched_count=0)

    def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                del self.docs[i]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self): self.cols = {}
    def __getitem__(self, name): return self.cols.setdefault(name, _FakeCol())


@pytest.fixture
def db(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(conns, "get_db", lambda: fake)
    monkeypatch.setattr(actions, "get_db", lambda: fake)
    return fake


@pytest.fixture
def crypto_on(monkeypatch):
    from cryptography.fernet import Fernet
    f = Fernet(Fernet.generate_key())
    monkeypatch.setattr(crypto, "_fernet", lambda: f)


def _flag(monkeypatch, on: bool):
    monkeypatch.setattr(conns, "get_settings",
                        lambda: SimpleNamespace(mcp_actions_enabled=on))


# ─── Flag gate ────────────────────────────────────────────────────────────────

def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(conns, "get_settings",
                        lambda: SimpleNamespace(mcp_actions_enabled=False))
    assert conns.mcp_enabled() is False


def test_queue_action_refuses_when_off(db, monkeypatch):
    _flag(monkeypatch, False)
    with pytest.raises(actions.McpActionsDisabled):
        actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                             {"when": "sat"}, "Book viewing")


# ─── Connections: encryption + tenant scope ──────────────────────────────────

def test_connection_token_encrypted_at_rest(db, crypto_on):
    conns.set_connection("Lekki Crest", "google_calendar",
                         "https://mcp.example/cal", token="super-secret")
    raw = db["client_connections"].find_one({"provider": "google_calendar"})
    assert raw["token_enc"] and raw["token_enc"] != "super-secret"
    resolved = conns.resolve_connection("Lekki Crest", "google_calendar")
    assert resolved["token"] == "super-secret"          # round-trips


def test_connection_is_case_insensitive_on_client(db, crypto_on):
    conns.set_connection("Lekki Crest", "google_calendar", "https://x", token="t")
    assert conns.get_connection("lekki crest", "google_calendar") is not None


def test_connection_tenant_scoped(db, crypto_on):
    conns.set_connection("Lekki Crest", "google_calendar", "https://x", token="t")
    assert conns.get_connection("Other Co", "google_calendar") is None
    assert conns.list_connections("Other Co") == []
    assert conns.resolve_connection("Other Co", "google_calendar") is None


def test_public_view_hides_secret(db, crypto_on):
    conns.set_connection("Lekki Crest", "zoho_crm", "https://z", token="t")
    view = conns.list_connections("Lekki Crest")[0]
    assert "token_enc" not in view and "token" not in view
    assert view["has_token"] is True and view["label"] == "Zoho CRM"


def test_disabled_connection_does_not_resolve(db, crypto_on):
    conns.set_connection("Lekki Crest", "google_calendar", "https://x",
                         token="t", enabled=False)
    assert conns.resolve_connection("Lekki Crest", "google_calendar") is None


def test_refuses_token_without_encryption(db, monkeypatch):
    monkeypatch.setattr(crypto, "_fernet", lambda: None)   # no key
    assert crypto.available() is False
    with pytest.raises(RuntimeError):
        conns.set_connection("Lekki Crest", "google_calendar", "https://x", token="t")


def test_no_auth_connection_needs_no_key(db, monkeypatch):
    monkeypatch.setattr(crypto, "_fernet", lambda: None)
    conns.set_connection("Lekki Crest", "notion", "https://n", auth_type="none")
    resolved = conns.resolve_connection("Lekki Crest", "notion")
    assert resolved["token"] is None and resolved["auth_type"] == "none"


# ─── Propose -> approve -> execute ───────────────────────────────────────────

def _connect(db, monkeypatch, crypto_on):
    _flag(monkeypatch, True)
    conns.set_connection("Lekki Crest", "google_calendar",
                         "https://mcp.example/cal", token="t")


def test_queue_action_requires_connection(db, crypto_on, monkeypatch):
    _flag(monkeypatch, True)   # flag on, but nothing connected
    with pytest.raises(actions.McpConnectionMissing):
        actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                             {"when": "sat"}, "Book viewing")


def test_queue_action_stages_pending(db, crypto_on, monkeypatch):
    _connect(db, monkeypatch, crypto_on)
    aid = actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                               {"when": "sat"}, "Book viewing for Mr Adewale")
    pend = actions.get_pending_actions("Lekki Crest")
    assert len(pend) == 1
    doc = pend[0]
    assert doc["kind"] == "action"
    assert doc["status"] == actions.ActionStatus.PENDING
    assert doc["action"]["tool"] == "create_event"
    assert doc["summary"].startswith("Book viewing")


def test_actions_excluded_from_message_queue(db, crypto_on, monkeypatch):
    """An action must never surface in the message-draft queue (it would be
    'sent' as a message). hitl.get_pending filters kind != action."""
    _connect(db, monkeypatch, crypto_on)
    actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                         {"when": "sat"}, "Book viewing")
    import tools.hitl as hitl
    monkeypatch.setattr(hitl, "get_db", lambda: db)
    assert hitl.get_pending() == []


def test_approve_then_execute_success(db, crypto_on, monkeypatch):
    _connect(db, monkeypatch, crypto_on)
    aid = actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                               {"when": "sat"}, "Book viewing")
    approved = actions.approve_action(aid)
    assert approved["status"] == actions.ActionStatus.APPROVED

    import tools.mcp_client as mcpc
    async def _ok(conn, name, args):
        return {"ok": True, "result": {"event_id": "evt_1"}}
    monkeypatch.setattr(mcpc, "call_tool", _ok)

    res = asyncio.run(actions.execute_approved_action(approved))
    assert res["ok"] is True
    final = db["pending_approvals"].find_one({"action.tool": "create_event"})
    assert final["status"] == actions.ActionStatus.EXECUTED
    assert final["action_result"]["result"]["event_id"] == "evt_1"


def test_execute_refuses_unapproved(db, crypto_on, monkeypatch):
    _connect(db, monkeypatch, crypto_on)
    aid = actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                               {"when": "sat"}, "Book viewing")
    pending = actions.get_pending_actions("Lekki Crest")[0]   # still pending
    res = asyncio.run(actions.execute_approved_action(pending))
    assert res["ok"] is False                                 # never executes


def test_execute_records_failure(db, crypto_on, monkeypatch):
    _connect(db, monkeypatch, crypto_on)
    aid = actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                               {"when": "sat"}, "Book viewing")
    approved = actions.approve_action(aid)
    import tools.mcp_client as mcpc
    async def _fail(conn, name, args):
        return {"ok": False, "error": "remote 500"}
    monkeypatch.setattr(mcpc, "call_tool", _fail)
    res = asyncio.run(actions.execute_approved_action(approved))
    assert res["ok"] is False
    final = db["pending_approvals"].find_one({"action.tool": "create_event"})
    assert final["status"] == actions.ActionStatus.FAILED
    assert final["action_result"]["error"] == "remote 500"


def test_skip_action(db, crypto_on, monkeypatch):
    _connect(db, monkeypatch, crypto_on)
    aid = actions.queue_action("Lekki Crest", "google_calendar", "create_event",
                               {"when": "sat"}, "Book viewing")
    actions.skip_action(aid)
    assert actions.get_pending_actions("Lekki Crest") == []
