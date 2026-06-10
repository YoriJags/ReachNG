"""v2 SHARP MODE drip — sequence helpers + stop-on-reply. Pure-function/mocked."""
from __future__ import annotations

import services.reachng_self_outreach as so
import tools.memory as memory
from tools.memory import Status


# ── Sequence helpers ─────────────────────────────────────────────────────────

def test_prev_capability_none_on_touch_one():
    assert so.prev_capability_for("real_estate", 1) is None


def test_prev_capability_real_estate_touch_two():
    cap = so.prev_capability_for("real_estate", 2)
    assert cap and "warm-buyer" in cap


def test_prev_capability_unknown_vertical_falls_back_to_general():
    assert so.prev_capability_for("space_tourism", 2) == so._T1_CAPABILITY_BY_VERTICAL["general"]


def test_prev_capability_normalizes_separators():
    # "Fashion / Retail" → fashion
    assert so.prev_capability_for("Fashion", 2) == so.prev_capability_for("retail", 2)


def test_followup_spacing():
    assert so.followup_days_after_touch(1) == 3      # touch 1 sent → touch 2 in 3d
    assert so.followup_days_after_touch(2) == 5      # touch 2 sent → touch 3 in 5d (~8d total)
    assert so.followup_days_after_touch(3) is None   # sequence done


# ── Stop-on-reply helper ─────────────────────────────────────────────────────

class _FakeContacts:
    def __init__(self):
        self.last_query = None
        self.last_update = None

    def update_many(self, query, update):
        self.last_query = query
        self.last_update = update

        class _Res:
            modified_count = 2
        return _Res()


def test_stop_followups_marks_replied(monkeypatch):
    fake = _FakeContacts()
    monkeypatch.setattr(memory, "get_contacts", lambda: fake)

    n = memory.stop_followups_for_email("Tunde@Example.com")
    assert n == 2
    # Only in-flight contacts are touched
    assert fake.last_query["status"]["$in"] == [Status.CONTACTED, Status.NOT_CONTACTED]
    sets = fake.last_update["$set"]
    assert sets["status"] == Status.REPLIED
    assert sets["next_followup_at"] is None
    assert sets["followup_stop_reason"] == "replied"


def test_stop_followups_bounce_opts_out(monkeypatch):
    fake = _FakeContacts()
    monkeypatch.setattr(memory, "get_contacts", lambda: fake)

    memory.stop_followups_for_email("dead@nowhere.ng", reason="bounced")
    sets = fake.last_update["$set"]
    assert sets["status"] == Status.OPTED_OUT
    assert sets["replied_at"] is None


def test_stop_followups_ignores_garbage(monkeypatch):
    fake = _FakeContacts()
    monkeypatch.setattr(memory, "get_contacts", lambda: fake)
    assert memory.stop_followups_for_email("not-an-email") == 0
    assert memory.stop_followups_for_email("") == 0


# ── Reply poller dormant without creds ───────────────────────────────────────

def test_reply_poll_dormant_without_creds(monkeypatch):
    import services.outreach_reply_poll as orp

    class _S:
        outreach_imap_host = None
        outreach_imap_user = None
        outreach_imap_password = None
        outreach_imap_port = 993
    monkeypatch.setattr(orp, "get_settings", lambda: _S())

    assert orp.outreach_reply_polling_enabled() is False
    assert orp.poll_outreach_replies() == {"skipped": "not_configured"}
