"""
Client-portal feeds — the data behind the Money + Reports tabs.

Each function is scoped to one client and defensive (missing collections never
raise). Reuses the exact shapes other modules already write:
  • receipt_matches  {client_name, status:"confirmed", confirmed_at, amount_ngn, from_phone}
  • paystack_events  {client_name, event:"charge.success", paid_at, amount_ngn}
  • contacts         {client_name, closed_by_client, deal_value_ngn, updated_at}
  • brief_sends      {client_name, day_str, sent_at}
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import structlog

from database import get_db

log = structlog.get_logger()

# Savings model (clearly an estimate, surfaced as "est." in the UI).
MINUTES_PER_HANDLED_MSG = 4
NGN_PER_HOUR = 2000          # ~ a Lagos VA hour


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else (v if isinstance(v, str) else None)


def payments_for(client_name: str, client_id: str | None = None, days: int = 30, limit: int = 25) -> dict:
    """Confirmed receipts (Receipt Catcher) + Paystack charges, newest first."""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    items, total = [], 0.0

    try:
        if "receipt_matches" in db.list_collection_names():
            q = {"status": "confirmed", "confirmed_at": {"$gte": since}}
            scope = [{"client_name": client_name}]
            if client_id:
                scope.append({"client_id": client_id})
            q["$or"] = scope
            for r in db["receipt_matches"].find(
                q, {"amount_ngn": 1, "from_phone": 1, "confirmed_at": 1, "matched_kind": 1}
            ).sort("confirmed_at", -1).limit(limit):
                amt = float(r.get("amount_ngn") or 0)
                total += amt
                items.append({
                    "amount_ngn": amt,
                    "who":        r.get("from_phone") or "—",
                    "kind":       r.get("matched_kind") or "receipt",
                    "at":         _iso(r.get("confirmed_at")),
                    "source":     "receipt",
                })
    except Exception as e:
        log.warning("payments_receipts_failed", error=str(e))

    try:
        if "paystack_events" in db.list_collection_names():
            for p in db["paystack_events"].find(
                {"client_name": client_name, "event": "charge.success", "paid_at": {"$gte": since}},
                {"amount_ngn": 1, "paid_at": 1, "customer_email": 1},
            ).sort("paid_at", -1).limit(limit):
                amt = float(p.get("amount_ngn") or 0)
                total += amt
                items.append({
                    "amount_ngn": amt,
                    "who":        p.get("customer_email") or "—",
                    "kind":       "card/transfer",
                    "at":         _iso(p.get("paid_at")),
                    "source":     "paystack",
                })
    except Exception as e:
        log.warning("payments_paystack_failed", error=str(e))

    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"count": len(items), "total_ngn": total, "items": items[:limit], "window_days": days}


def bookings_for(client_name: str, days: int = 30, limit: int = 25) -> dict:
    """Deals/bookings the client marked closed, newest first."""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    items, total = [], 0.0
    try:
        for c in db["contacts"].find(
            {"client_name": client_name, "closed_by_client": True, "updated_at": {"$gte": since}},
            {"name": 1, "deal_value_ngn": 1, "updated_at": 1, "vertical": 1},
        ).sort("updated_at", -1).limit(limit):
            val = float(c.get("deal_value_ngn") or 0)
            total += val
            items.append({
                "name":       c.get("name") or "—",
                "value_ngn":  val,
                "at":         _iso(c.get("updated_at")),
            })
    except Exception as e:
        log.warning("bookings_failed", error=str(e))
    return {"count": len(items), "total_ngn": total, "items": items, "window_days": days}


def savings_for(client_name: str, days: int = 30) -> dict:
    """Estimated hours + ₦ saved from messages EYO handled (drafted/sent)."""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    handled = 0
    try:
        if "approvals" in db.list_collection_names():
            handled += db["approvals"].count_documents({
                "client_name": client_name,
                "status": {"$in": ["approved", "auto_sent", "edited"]},
                "actioned_at": {"$gte": since},
            })
    except Exception as e:
        log.warning("savings_approvals_failed", error=str(e))
    try:
        if "outreach_log" in db.list_collection_names():
            handled += db["outreach_log"].count_documents({
                "client_name": client_name, "sent_at": {"$gte": since},
            })
    except Exception as e:
        log.warning("savings_outreach_failed", error=str(e))

    minutes = handled * MINUTES_PER_HANDLED_MSG
    hours = round(minutes / 60.0, 1)
    return {
        "messages_handled": handled,
        "hours_saved":      hours,
        "cost_saved_ngn":   int(hours * NGN_PER_HOUR),
        "window_days":      days,
        "estimate":         True,
    }


def brief_history_for(client_name: str, limit: int = 30) -> dict:
    """Recent Owner Brief sends + current streak."""
    db = get_db()
    items = []
    try:
        if "brief_sends" in db.list_collection_names():
            for b in db["brief_sends"].find(
                {"client_name": client_name}, {"day_str": 1, "sent_at": 1, "_id": 0}
            ).sort("sent_at", -1).limit(limit):
                items.append({"day": b.get("day_str"), "at": _iso(b.get("sent_at"))})
    except Exception as e:
        log.warning("brief_history_failed", error=str(e))
    streak = {"days": 0}
    try:
        from services.brief_streak import compute_streak
        streak = compute_streak(client_name)
    except Exception:
        pass
    return {"count": len(items), "items": items, "streak_days": streak.get("days", 0)}


def report_pdf_bytes(client_name: str, client_id: str | None = None, days: int = 30) -> bytes:
    """One-page PDF summary of the client's results. Reuses the live feeds +
    cash signals + deposits-caught. reportlab is already a dependency."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    def _ngn(n):
        return f"NGN {int(n or 0):,}"

    # Gather numbers (all defensive)
    cash = {}
    try:
        from tools.cash_signals import cash_signals_for
        cash = cash_signals_for(client_name)
    except Exception:
        pass
    deposits = 0
    try:
        from services.brief_streak import cumulative_deposits_ngn
        deposits = cumulative_deposits_ngn(client_name)
    except Exception:
        pass
    pay  = payments_for(client_name, client_id, days=days)
    book = bookings_for(client_name, days=days)
    save = savings_for(client_name, days=days)
    hist = brief_history_for(client_name)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 28 * mm

    c.setFillColorRGB(0.72, 0.36, 0.22)  # terracotta
    c.setFont("Helvetica-Bold", 20)
    c.drawString(22 * mm, y, "ReachNG — Results report")
    y -= 9 * mm
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica", 12)
    c.drawString(22 * mm, y, client_name)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.45, 0.42, 0.36)
    c.drawString(22 * mm, y - 5 * mm,
                 f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y')} · last {days} days")
    y -= 16 * mm

    rows = [
        ("Likely collectible now", _ngn(cash.get("collectible_total_ngn", 0))),
        ("Deposits caught (lifetime)", _ngn(deposits)),
        ("Payments logged", f"{pay['count']} · {_ngn(pay['total_ngn'])}"),
        ("Bookings/deals closed", f"{book['count']} · {_ngn(book['total_ngn'])}"),
        ("Messages EYO handled", str(save["messages_handled"])),
        ("Hours saved (est.)", f"{save['hours_saved']} hrs ≈ {_ngn(save['cost_saved_ngn'])}"),
        ("Owner Brief streak", f"{hist['streak_days']} days"),
    ]
    c.setFont("Helvetica", 11)
    for label, val in rows:
        c.setFillColorRGB(0.45, 0.42, 0.36)
        c.drawString(22 * mm, y, label)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(w - 22 * mm, y, val)
        c.setFont("Helvetica", 11)
        y -= 9 * mm
        c.setStrokeColorRGB(0.91, 0.87, 0.78)
        c.line(22 * mm, y + 3 * mm, w - 22 * mm, y + 3 * mm)

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.6, 0.57, 0.5)
    c.drawString(22 * mm, 18 * mm,
                 "Every message is human-approved before sending. Hours/₦ saved are estimates.")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.72, 0.36, 0.22)
    c.drawRightString(w - 22 * mm, 18 * mm, "ReachNG")
    c.showPage()
    c.save()
    return buf.getvalue()
