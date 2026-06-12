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


# ── Copy-quality fixes (calibration session findings, 2026-06-12) ────────────

import services.reachng_self_outreach as so2


def test_scrub_bare_dashes_get_spaces():
    # The production bug: "lands—party size…—and" became "lands,party …,and"
    out = so2._scrub_dashes("it qualifies the reservation the moment an enquiry lands—party size, date, deposit ask—and drafts the reply")
    assert ",party" not in out and ",and" not in out
    assert "lands, party size, date, deposit ask, and drafts" in out


def test_scrub_keeps_numeric_ranges():
    assert so2._scrub_dashes("110–150 words") == "110-150 words"


def test_signature_normalized_when_jammed_inline():
    msg = "Hi Tunde,\n\nGreat product. There's a demo on our site. Best,\nYori\nFounder, ReachNG\nLagos · www.reachng.ng"
    out = so2._normalize_signature(msg)
    assert out.endswith("Best,\nYori\nFounder, ReachNG\nLagos · www.reachng.ng")
    assert "site.\n\nBest,\n" in out  # blank line before the sign-off


def test_signature_appended_when_missing():
    out = so2._normalize_signature("Hi team,\n\nShort note.")
    assert out.endswith("\n\nBest,\nYori\nFounder, ReachNG\nLagos · www.reachng.ng")


def test_lint_catches_saturday_cliche():
    hits = so2._lint_banned("Quick intro", "Saturday night enquiries get answered in minutes.")
    assert "saturday" in hits


def test_lint_clean_draft_passes():
    assert so2._lint_banned("Introducing ReachNG", "It drafts the reply when enquiries spike, waiting for your tap.") == []
