"""
MarketOS Engine — commodity price intelligence for Lagos traders.
Generates daily market briefings and buy/sell alerts via Claude.
Prices entered manually or fetched via Apify when token is available.
"""
import json
import anthropic
from datetime import datetime, timezone
from database import get_db
from config import get_settings
import structlog

log = structlog.get_logger()

COMMODITIES = [
    "maize", "cassava", "tomatoes", "palm_oil", "rice",
    "fertiliser", "diesel", "petrol",
]

MARKETS = ["mile_12", "oyingbo", "oshodi", "ketu", "mile_2"]


def get_prices_col():
    return get_db()["market_prices"]


def get_alerts_col():
    return get_db()["market_alerts"]


def record_price(commodity: str, market: str, price_ngn: float,
                 unit: str = "kg", source: str = "manual") -> str:
    now = datetime.now(timezone.utc)
    result = get_prices_col().insert_one({
        "commodity": commodity.lower(),
        "market":    market.lower(),
        "price_ngn": price_ngn,
        "unit":      unit,
        "source":    source,
        "recorded_at": now,
    })
    log.info("price_recorded", commodity=commodity, market=market, price=price_ngn)
    return str(result.inserted_id)


def get_latest_prices(commodity: str | None = None) -> list[dict]:
    """Return the most recent price entry per commodity+market combination."""
    pipeline = []
    if commodity:
        pipeline.append({"$match": {"commodity": commodity.lower()}})
    pipeline += [
        {"$sort": {"recorded_at": -1}},
        {"$group": {
            "_id": {"commodity": "$commodity", "market": "$market"},
            "price_ngn":    {"$first": "$price_ngn"},
            "unit":         {"$first": "$unit"},
            "recorded_at":  {"$first": "$recorded_at"},
            "source":       {"$first": "$source"},
        }},
        {"$sort": {"_id.commodity": 1, "_id.market": 1}},
    ]
    rows = list(get_prices_col().aggregate(pipeline))
    return [
        {
            "commodity":   r["_id"]["commodity"],
            "market":      r["_id"]["market"],
            "price_ngn":   r["price_ngn"],
            "unit":        r["unit"],
            "recorded_at": r["recorded_at"].isoformat() if hasattr(r.get("recorded_at"), "isoformat") else "",
        }
        for r in rows
    ]


def get_price_history(commodity: str, market: str, days: int = 7) -> list[dict]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list(
        get_prices_col()
        .find({"commodity": commodity.lower(), "market": market.lower(), "recorded_at": {"$gte": cutoff}})
        .sort("recorded_at", 1)
    )
    return [
        {"price_ngn": r["price_ngn"], "recorded_at": r["recorded_at"].isoformat()}
        for r in rows
    ]


def generate_daily_briefing(trader_name: str, commodities_watched: list[str]) -> str:
    """
    Generate a personalised WhatsApp daily market briefing for a trader.
    Uses latest prices from DB + Claude to write the brief.
    """
    prices = get_latest_prices()
    watched = [p for p in prices if p["commodity"] in [c.lower() for c in commodities_watched]]

    if not watched:
        return (
            f"Good morning {trader_name}! No price data yet for your commodities. "
            f"Prices will update as the market opens. Check back shortly."
        )

    price_lines = "\n".join(
        f"  - {p['commodity'].replace('_',' ').title()} @ {p['market'].replace('_',' ').title()}: "
        f"₦{p['price_ngn']:,.0f}/{p['unit']}"
        for p in watched
    )

    prompt = f"""You are MarketOS, a commodity price intelligence service for Lagos traders.

Write a short WhatsApp morning briefing for {trader_name}.

Today's prices:
{price_lines}

Guidelines:
- Start with "Good morning {trader_name.split()[0]}!"
- Highlight any prices that look unusually high or low
- Give one actionable observation (buy now / hold / watch)
- Nigerian English tone — direct and practical
- Max 5 lines. No bullet points (WhatsApp formatting)
- End with "— MarketOS" """

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def check_buy_alerts() -> list[dict]:
    """
    Check all active price alert thresholds.
    Returns list of triggered alerts with draft WhatsApp message.
    """
    alerts = list(get_alerts_col().find({"active": True}))
    triggered = []
    latest = {(p["commodity"], p["market"]): p["price_ngn"] for p in get_latest_prices()}

    for alert in alerts:
        commodity = alert["commodity"]
        market    = alert.get("market", "any")
        threshold = alert["threshold_ngn"]
        direction = alert.get("direction", "below")  # "below" = buy alert, "above" = sell/avoid alert

        if market == "any":
            prices_for_commodity = [v for (c, m), v in latest.items() if c == commodity]
            current_price = min(prices_for_commodity) if prices_for_commodity else None
        else:
            current_price = latest.get((commodity, market))

        if current_price is None:
            continue

        triggered_flag = (
            (direction == "below" and current_price <= threshold) or
            (direction == "above" and current_price >= threshold)
        )

        if triggered_flag:
            action = "BUY NOW" if direction == "below" else "HOLD — price is high"
            msg = (
                f"MarketOS Alert — {commodity.replace('_',' ').title()}\n"
                f"Current price: ₦{current_price:,.0f}/{alert.get('unit','kg')}\n"
                f"Your threshold: ₦{threshold:,.0f}\n"
                f"→ {action}"
            )
            triggered.append({
                "alert_id":    str(alert["_id"]),
                "trader_name": alert.get("trader_name", ""),
                "commodity":   commodity,
                "current_price": current_price,
                "threshold":   threshold,
                "direction":   direction,
                "message":     msg,
                "phone":       alert.get("phone", ""),
            })

    return triggered


def upsert_alert(trader_name: str, phone: str, commodity: str,
                 threshold_ngn: float, direction: str = "below",
                 market: str = "any", unit: str = "kg") -> str:
    now = datetime.now(timezone.utc)
    result = get_alerts_col().update_one(
        {"phone": phone, "commodity": commodity, "direction": direction},
        {
            "$set": {
                "trader_name":  trader_name,
                "threshold_ngn": threshold_ngn,
                "market":       market,
                "unit":         unit,
                "active":       True,
                "updated_at":   now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    if result.upserted_id:
        return str(result.upserted_id)
    row = get_alerts_col().find_one({"phone": phone, "commodity": commodity, "direction": direction})
    return str(row["_id"]) if row else ""
