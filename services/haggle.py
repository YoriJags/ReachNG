"""
EYO Haggle — negotiation engine (invention #2).

Nigerian commerce runs on negotiation ("last price?", "ah, na so e cost?").
Haggle runs the back-and-forth to a close against an owner-set **secret floor**
and **allowed sweeteners** — it never drops below the floor, prefers adding value
to cutting price, and hands the thread to the owner when a customer is stuck
below the floor or the rounds run out.

This module is the deterministic decision core (pure, no LLM): given the owner's
negotiation rules + the conversation state + the customer's latest number, it
returns the next move. A drafter turns the move into a message in the owner's
voice (wiring slice); `haggle_reply_text()` gives a usable deterministic fallback.

The floor is never revealed to the customer.
"""
from __future__ import annotations

from typing import Optional

ACCEPT      = "accept"
COUNTER     = "counter"
SWEETEN     = "hold_offer_sweetener"
HOLD        = "hold"
ESCALATE    = "escalate_owner"


def _round_ngn(n: float) -> int:
    return int(round(n))


def negotiate(rules: dict, *, customer_offer: Optional[float] = None,
              state: Optional[dict] = None) -> dict:
    """Decide the next negotiation move.

    rules: {
      list_price: float,           # starting / asking price
      floor_price: float,          # NEVER go below this (the secret floor)
      sweeteners: [str, ...],      # value-adds offered before cutting price
      max_rounds: int = 3,         # after this, hand to the owner
    }
    state: {round: int, last_offer: float}  # prior round + our last quoted price
    customer_offer: the number the customer proposed (None = vague "discount?" ask)

    Returns: {action, price, sweetener, rationale, round, next_state,
              below_floor_requested}
    """
    list_price = float(rules.get("list_price") or 0)
    floor = float(rules.get("floor_price") or 0)
    if floor > list_price:           # sanity — floor can't exceed list
        floor = list_price
    sweeteners = list(rules.get("sweeteners") or [])
    max_rounds = int(rules.get("max_rounds") or 3)

    state = state or {}
    rnd = int(state.get("round") or 0) + 1
    last_offer = float(state.get("last_offer") if state.get("last_offer") is not None else list_price)

    def out(action, price=None, sweetener=None, rationale="", below_floor=False):
        keep = last_offer if price is None else price
        return {
            "action": action,
            "price": None if price is None else _round_ngn(price),
            "sweetener": sweetener,
            "rationale": rationale,
            "round": rnd,
            "below_floor_requested": below_floor,
            "next_state": {"round": rnd, "last_offer": _round_ngn(keep)},
        }

    # Customer is at or above list — close it.
    if customer_offer is not None and customer_offer >= list_price:
        return out(ACCEPT, price=list_price, rationale="Customer is at or above list price.")

    # Rounds exhausted — hand to the owner.
    if rnd > max_rounds:
        return out(ESCALATE, price=last_offer,
                   rationale="Max negotiation rounds reached without a deal.")

    # Vague discount ask (no number) — hold price, add value first.
    if customer_offer is None:
        if sweeteners:
            return out(SWEETEN, price=last_offer, sweetener=sweeteners[0],
                       rationale="Discount asked without a number — hold price, lead with a sweetener.")
        return out(HOLD, price=last_offer, rationale="Discount asked; hold at current price.")

    # Offer below the floor — cannot meet there. Hold our current price (never
    # chase down to the floor) and add value; escalate if they stay stuck.
    if customer_offer < floor:
        if sweeteners and rnd <= max_rounds - 1:
            idx = min(rnd - 1, len(sweeteners) - 1)
            return out(SWEETEN, price=last_offer, sweetener=sweeteners[idx],
                       rationale="Offer is below your floor — hold price, add value.",
                       below_floor=True)
        return out(ESCALATE, price=last_offer,
                   rationale="Customer is stuck below your floor.", below_floor=True)

    # Offer is between floor and list — meet in the middle, never below floor.
    counter = max(floor, (last_offer + customer_offer) / 2.0)
    # If the gap to their offer is small, take the deal (at their number, which clears the floor).
    if (counter - customer_offer) <= max(1.0, list_price * 0.02):
        return out(ACCEPT, price=max(floor, customer_offer),
                   rationale="Their offer clears the floor and is within a fair middle — close it.")
    return out(COUNTER, price=counter,
               rationale="Counter between our last price and their offer; never below floor.")


def haggle_reply_text(move: dict, *, agent_name: str = "EYO",
                      close_line: str = "Shall I lock it in for you?") -> str:
    """Deterministic customer-facing phrasing for a move (LLM drafter can replace).

    Never mentions the floor. For ESCALATE, returns a neutral holding line —
    the owner is prompted separately to decide whether to break the floor.
    """
    action = move.get("action")
    price = move.get("price")
    price_s = f"₦{price:,.0f}" if price is not None else "that"
    sweetener = move.get("sweetener")

    if action == ACCEPT:
        return f"Done — {price_s} works. {close_line}"
    if action == COUNTER:
        return f"I hear you. I can do {price_s} — that's the best I can stretch on price. {close_line}"
    if action == SWEETEN:
        return (f"The price holds at {price_s}, but I'll add {sweetener} to make it worth your while. "
                f"{close_line}")
    if action == HOLD:
        return f"Our price is {price_s} — and honestly it's worth every naira. {close_line}"
    # ESCALATE — neutral holding line to the customer
    return "Let me confirm the very best I can do and come right back to you shortly."


def owner_escalation_text(move: dict, contact_name: Optional[str],
                          customer_offer: Optional[float], floor_price: float) -> str:
    """Owner-facing prompt when Haggle escalates — the owner decides on the floor."""
    who = contact_name or "A customer"
    offer_s = f"₦{customer_offer:,.0f}" if customer_offer else "below your floor"
    return (f"💬 {who} is pushing to {offer_s} — under your floor of ₦{floor_price:,.0f}. "
            f"EYO held the line. Want it to stand firm, or can it go lower?")


def owner_haggle_prompt(move: dict, contact_name: Optional[str],
                        customer_offer: Optional[float],
                        product: Optional[str] = None) -> str:
    """Owner-first prompt on ANY price haggle: surface the customer's offer + EYO's
    suggested move, then hand the call back to the owner to set the fair price or
    option. The owner stays in control of the number — EYO only suggests."""
    who = contact_name or "A customer"
    prod = f" on {product}" if product else ""
    offer_s = f" (offered ₦{customer_offer:,.0f})" if customer_offer else ""
    price = move.get("price")
    price_s = f"₦{price:,.0f}" if price is not None else "your current price"
    sweetener = move.get("sweetener")
    action = move.get("action")
    if action == ACCEPT:
        suggestion = f"accept at {price_s}"
    elif action == COUNTER:
        suggestion = f"counter at {price_s}"
    elif action == SWEETEN:
        suggestion = f"hold {price_s} and add {sweetener}" if sweetener else f"hold {price_s}"
    else:  # HOLD
        suggestion = f"hold at {price_s}"
    return (f"💬 {who} is negotiating{prod}{offer_s}. EYO suggests {suggestion}. "
            f"What's your fair price or option? Approve or edit EYO's draft before it goes out.")
