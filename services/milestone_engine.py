"""
Milestone Engine — turns silent KPIs into shareable moments.

Watches each client's scorecard for milestone thresholds. On hit:
  1. Persists a `milestone_events` doc so we never re-fire the same milestone.
  2. Drafts a celebratory tweet/LinkedIn post the owner can one-tap share.
  3. Renders a shareable card (HTML page) the owner can screenshot.
  4. Queues a congratulatory WhatsApp to the owner with the card link + draft tweet.

Most owners won't share. The 20% who do compound ReachNG's reputation faster
than any paid acquisition. The 80% still get the dopamine moment in their
WhatsApp inbox.

Milestones tracked
------------------
  • first_naira       — first ₦ closed via ReachNG
  • first_million     — ₦1M cumulative closed
  • first_5_million   — ₦5M cumulative
  • first_10_million  — ₦10M cumulative
  • first_50_million  — ₦50M cumulative
  • bookings_10       — 10th booking closed
  • bookings_50
  • bookings_100
  • bookings_500
  • drafts_1000       — 1000th draft approved
  • day_30            — 30-day anniversary
  • day_90            — 90 days on the platform
  • day_365           — one year

Adding more is a one-line dict entry below.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from database import get_db
from services.scorecard import compute_scorecard, format_ngn

log = structlog.get_logger()


# ─── Definitions ──────────────────────────────────────────────────────────────

# Threshold milestones. Each evaluator pulls a single scalar from the cumulative
# scorecard (window=10 years to capture lifetime) and fires when scalar >= threshold.

LIFETIME_DAYS = 365 * 10


def _eval_lifetime(client_id: str):
    """Compute a long-window scorecard so cumulative totals are accurate."""
    try:
        return compute_scorecard(client_id, period_days=LIFETIME_DAYS)
    except Exception:
        return None


MILESTONES = [
    # key                threshold  evaluator(sc)
    ("first_naira",         1,        lambda sc: float(sc.ngn_closed or 0)),
    ("first_million",       1_000_000,  lambda sc: float(sc.ngn_closed or 0)),
    ("first_5_million",     5_000_000,  lambda sc: float(sc.ngn_closed or 0)),
    ("first_10_million",   10_000_000,  lambda sc: float(sc.ngn_closed or 0)),
    ("first_50_million",   50_000_000,  lambda sc: float(sc.ngn_closed or 0)),
    ("bookings_10",          10,         lambda sc: int(sc.bookings_closed or 0)),
    ("bookings_50",          50,         lambda sc: int(sc.bookings_closed or 0)),
    ("bookings_100",        100,         lambda sc: int(sc.bookings_closed or 0)),
    ("bookings_500",        500,         lambda sc: int(sc.bookings_closed or 0)),
    ("drafts_1000",       1000,         lambda sc: int(sc.drafts_approved or 0)),
]


# Day-anniversary milestones — separate logic
DAY_MILESTONES = [30, 90, 365]


# ─── Collections ──────────────────────────────────────────────────────────────

def _db():
    return get_db()


def get_events_col():
    return _db()["milestone_events"]


def ensure_milestone_indexes() -> None:
    col = get_events_col()
    col.create_index([("client_id", ASCENDING), ("key", ASCENDING)], unique=True)
    col.create_index([("fired_at", DESCENDING)])


# ─── Card render ──────────────────────────────────────────────────────────────

def _card_html(client: dict, key: str, headline: str, sub: str) -> str:
    name = client.get("name", "Your business")
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{name} — {headline}</title>
<style>
  body{{margin:0;background:#0a0a0a;color:#fff;font-family:-apple-system,system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:40px;}}
  .card{{max-width:720px;background:linear-gradient(135deg,#1a0e05 0%,#0a0a0a 70%);border:1px solid #ff5500;border-radius:18px;padding:48px;text-align:center;box-shadow:0 0 80px rgba(255,85,0,0.18);}}
  .eyebrow{{font-size:11px;color:#ff5500;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin-bottom:18px;}}
  h1{{font-size:48px;line-height:1.05;margin:0 0 14px;letter-spacing:-1.2px;color:#fff;}}
  .sub{{font-size:18px;color:#bdbdbd;margin:0 0 28px;}}
  .biz{{font-size:14px;color:#9aa0a8;margin-top:18px;}}
  .logo{{font-size:14px;font-weight:800;letter-spacing:-0.2px;color:#fff;}}
  .logo span{{color:#ff5500;}}
  .stamp{{margin-top:32px;padding-top:24px;border-top:1px solid #2a3340;font-size:11px;color:#6a7280;letter-spacing:0.06em;}}
</style></head><body>
<div class="card">
  <div class="eyebrow">Milestone unlocked</div>
  <h1>{headline}</h1>
  <p class="sub">{sub}</p>
  <p class="biz">{name}</p>
  <div class="stamp">
    Powered by <span class="logo">Reach<span style="color:#ff5500;">NG</span></span> · {datetime.now(timezone.utc).strftime('%d %b %Y')}
  </div>
</div></body></html>"""


# ─── Tweet drafter ────────────────────────────────────────────────────────────

_TWEET_BLURBS = {
    "first_naira":      ("First ₦ closed via my ReachNG agent.",                     "Quietly proud."),
    "first_million":    ("My ReachNG agent just crossed ₦1M closed.",                "All from WhatsApp replies I tapped approve on. Wild."),
    "first_5_million":  ("₦5M closed via my ReachNG agent.",                          "I'm still typing about 10% of these. The other 90% — just a tap."),
    "first_10_million": ("₦10M closed via my ReachNG agent.",                         "Lagos SME life shouldn't include answering DMs at midnight. Sorted."),
    "first_50_million": ("₦50M through my ReachNG agent.",                            "Whatever I'm paying these guys isn't enough."),
    "bookings_10":      ("10th booking closed by my ReachNG agent.",                  "Each one I just tapped approve from my phone."),
    "bookings_50":      ("50 bookings closed by my ReachNG agent.",                   "The 'are you serious about this?' replies, finally going out in seconds."),
    "bookings_100":     ("100 bookings via my ReachNG agent.",                        "I should be the one paying the agent."),
    "bookings_500":     ("500 bookings through my ReachNG agent.",                    "Yes the customer thinks I typed it. No I did not."),
    "drafts_1000":      ("My ReachNG agent has drafted 1,000 personalised WhatsApp replies for my business.", "I approved each one. About 2 minutes' typing each = 33 hours of my life back."),
    "day_30":           ("30 days on ReachNG. Verdict: it works.",                    "Couldn't go back to typing replies one by one."),
    "day_90":           ("90 days on ReachNG.",                                       "Now baked into how the business runs. Highly recommended."),
    "day_365":          ("One year on ReachNG.",                                       "Genuinely couldn't imagine going back."),
}


def _draft_tweet(key: str, sc) -> str:
    blurb, line2 = _TWEET_BLURBS.get(key, ("Milestone unlocked on my ReachNG agent.", ""))
    extra = ""
    if "million" in key and sc:
        extra = f"\n\n{format_ngn(sc.ngn_closed)} closed · {sc.bookings_closed} bookings · {sc.hours_saved:.0f}h of typing saved."
    return f"{blurb}\n\n{line2}{extra}\n\nbuilt by @reachng_"


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def check_milestones_for_client(client_id: str) -> list[dict]:
    """Evaluate every milestone for one client. Returns newly-fired events."""
    db = _db()
    client = db["clients"].find_one({"_id": ObjectId(client_id)})
    if not client:
        return []
    sc = _eval_lifetime(client_id)
    if not sc:
        return []

    events = get_events_col()
    fired_keys = {e["key"] for e in events.find({"client_id": client_id}, {"key": 1})}
    new: list[dict] = []
    now = datetime.now(timezone.utc)

    # Threshold milestones
    for key, threshold, fn in MILESTONES:
        if key in fired_keys:
            continue
        try:
            value = fn(sc)
        except Exception:
            continue
        if value >= threshold:
            event = _record_event(client, key, value, threshold, sc)
            if event:
                new.append(event)

    # Day-anniversary milestones
    onboarded = client.get("onboarded_at")
    if isinstance(onboarded, datetime):
        if onboarded.tzinfo is None:
            onboarded = onboarded.replace(tzinfo=timezone.utc)
        days_active = (now - onboarded).days
        for n in DAY_MILESTONES:
            key = f"day_{n}"
            if key in fired_keys:
                continue
            if days_active >= n:
                event = _record_event(client, key, days_active, n, sc)
                if event:
                    new.append(event)
    return new


def _record_event(client: dict, key: str, value, threshold, sc) -> Optional[dict]:
    """Persist a milestone event + draft the celebratory ack."""
    now = datetime.now(timezone.utc)
    client_id = str(client["_id"])

    # Build the human-facing headline + sub
    headline, sub = _headline_for(key, sc)

    event_doc = {
        "client_id":      client_id,
        "client_name":    client.get("name"),
        "key":            key,
        "value":          value,
        "threshold":      threshold,
        "headline":       headline,
        "sub":            sub,
        "tweet_draft":    _draft_tweet(key, sc),
        "card_html":      _card_html(client, key, headline, sub),
        "fired_at":       now,
        "shared":         False,
    }
    try:
        get_events_col().insert_one(event_doc)
    except Exception as e:
        # Unique index conflict — already fired (race condition). Skip silently.
        log.info("milestone_already_fired", client=client.get("name"), key=key)
        return None

    log.info("milestone_fired", client=client.get("name"), key=key, value=value)

    # Queue a celebratory WhatsApp to the owner via HITL
    owner_phone = client.get("owner_phone")
    if owner_phone:
        msg = (
            f"🎉 {headline} — {sub}\n\n"
            f"Want to share the moment? Here's a draft post you can copy:\n\n"
            f"{event_doc['tweet_draft']}"
        )
        try:
            from tools.hitl import queue_draft
            queue_draft(
                contact_id=client_id,
                contact_name=(client.get("owner_name") or client.get("name") or "Owner"),
                vertical=client.get("vertical") or "general",
                channel="whatsapp",
                message=msg,
                phone=owner_phone,
                source="milestone",
                client_name=client.get("name"),
            )
        except Exception as _e:
            log.warning("milestone_ack_queue_failed", client=client.get("name"), error=str(_e))

    event_doc["_id"] = "stored"   # avoid bson-leak when returning
    event_doc.pop("card_html", None)  # too verbose for return
    return event_doc


def _headline_for(key: str, sc) -> tuple[str, str]:
    if key == "first_naira":
        return "First naira closed.", "The agent just billed its first booking."
    if key.startswith("first_"):
        mapping = {"first_million": "₦1M", "first_5_million": "₦5M",
                   "first_10_million": "₦10M", "first_50_million": "₦50M"}
        label = mapping.get(key, "Big number")
        return f"{label} closed.", f"Cumulative ReachNG-handled cash crossed {label}."
    if key.startswith("bookings_"):
        n = key.split("_")[1]
        return f"{n} bookings closed.", "Every one personalised. Every one you approved."
    if key == "drafts_1000":
        return "1,000 drafts approved.", "That's roughly 33 hours of typing saved."
    if key.startswith("day_"):
        d = key.split("_")[1]
        return f"{d} days on ReachNG.", "An anniversary worth marking."
    return "Milestone unlocked.", ""


def check_milestones_all_clients() -> dict:
    db = _db()
    fired = 0
    scanned = 0
    for c in db["clients"].find({"active": True}, {"_id": 1}):
        scanned += 1
        try:
            new = check_milestones_for_client(str(c["_id"]))
            fired += len(new)
        except Exception as e:
            log.warning("milestone_check_failed", client_id=str(c["_id"]), error=str(e))
    log.info("milestone_sweep_done", scanned=scanned, fired=fired)
    return {"scanned": scanned, "fired": fired}
