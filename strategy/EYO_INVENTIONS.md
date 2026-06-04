# EYO — Net-New Inventions (build queue)

Five net-new edges on the existing ReachNG engine. Meta's Jun 2026 Business
Agent commoditised generic WhatsApp chat — each invention below does something
Meta's horizontal agent structurally **can't**, and each sits on capabilities we
already shipped.

**Build order:** Shield → Haggle → Radar → Cashflow → Referral.
(Shield = fastest "wow" on shipped vision; Haggle = deepest moat.)

These are net-new — NOT the already-shipped Vault / Voice safe-switch / Money-Leak.

---

## Shared engine (already exists — what each invention builds on)

| Capability | Module / collection |
|---|---|
| Inbound WhatsApp (Meta Cloud API + Unipile) | `tools/reply_router.py`, `tools/inbound_media.py` |
| Receipt OCR (Haiku vision) | `tools/receipt_vision.py` → `receipt_matches` |
| Voice transcription | `tools/voice_whisper.py` |
| Intent / emotion classifier | `services/inbound_classifier.py` |
| Per-customer memory (Vault + NBA) | `services/vault.py`, `tools/memory.py` |
| Money leak / rescue | `services/money_leak.py` |
| Owner brief + cash signals | `tools/morning_brief_client.py`, `tools/cash_signals.py` |
| HITL drafting (the choke point) | `tools/hitl.py::queue_draft` |
| Business brief (tone / pricing_rules / guardrails) | `services/brief.py` |
| Outcome learning (win/miss loop) | `services/outcome_learning.py` |
| Link tracking | `/hi/{slug}` attribution |
| Scheduler (Africa/Lagos) | `scheduler.py` (APScheduler) |

Every invention preserves HITL (nothing sends without owner approval unless
Autopilot is earned) and is vertical-agnostic (hospitality, retail, EstateOS,
TalentOS).

---

## 1 · EYO Shield — fake-transfer / scam detector  **[build first]**

**What:** before goods leave, flag suspect "I've paid" screenshots — photoshop
signs, "pending"/unconfirmed status, amount/recipient mismatch, duplicate/reused
image, and repeat offenders in the client's own history.

**Reuses:** `receipt_vision` (already OCRs receipts), `receipt_matches`
(amount/recipient), Vault (per-customer history), HITL (warn, don't auto-act).

**New pieces:**
- `services/shield.py` → `assess_transfer(client, from_phone, image, expected_amount=None) -> {risk, reasons[]}`. Signals: status text ("pending"/"in progress"), amount vs expected/ledger, bank/recipient name vs the client's own account, perceptual-hash duplicate vs prior receipts, velocity (same image/amount across contacts), sender's prior fraud flags.
- Hook into the inbound-image path: high risk → owner alert ("⚠️ Possible fake transfer from X — verify before releasing") + `receipt_matches.status = "suspect"`.

**Data:** add `phash`, `risk`, `risk_reasons` to `receipt_matches`; `fraud_flags` count on the Vault customer.
**Surface:** owner-brief line + portal Money "flagged transfers" + Vault fraud badge.
**Safety:** never auto-decline; EYO warns, owner decides.
**Meta edge:** Meta's pipe has no bank / ledger / history context. Pure Naija money-protection.
**Effort:** M (vision shipped; add scoring + phash + alert).

---

## 2 · EYO Haggle — negotiation engine

**What:** runs Nigerian price negotiation to a close against an owner-set
**secret floor + allowed sweeteners**; knows when to hold, concede, or walk.

**Reuses:** drafter/HITL, brief `pricing_rules`, classifier (haggle-intent), Vault (customer value).

**New pieces:**
- Brief: structured `negotiation` block — `list_price`, `floor_price`, `never_below`, `sweeteners[]`, `walk_away_signals`, `max_rounds`. (extend `services/brief.py` + the portal brief UI)
- `services/haggle.py` → `negotiate(client, contact, inbound, negotiation_rules, history) -> {draft, state}`. Tracks round count + concession ladder; refuses below floor; offers a sweetener **before** a price cut; escalates to the owner near the floor.
- State on the contact: `haggle_round`, `last_offer`.

**Surface:** Approvals shows "negotiation · round 2 · floor ₦80k"; owner sees the ladder.
**Safety:** each counter drafted for approval; autopilot only once earned.
**Meta edge:** generic agent quotes list price and folds; never guards a hidden floor or haggles in Naija cadence. **Deepest moat.**
**Effort:** M–L (negotiation brief + state machine).

---

## 3 · EYO Radar — demand intelligence from the aggregate inbox

**What:** reads **all** inbound across customers and briefs the **owner** on what
the market is asking — unmet demand, missing prices, trending requests, stockouts.

**Reuses:** classifier (intent/topic tags), memory, owner brief, `money_leak` (price-asked).

**New pieces:**
- `services/demand_radar.py` → aggregate last-N-days inbound by product/topic mention → cluster (Haiku batch or keyword+embedding) → rank by frequency × intent. Detect "asked about X, no listed price/package."
- Output: weekly "Demand radar" — top requests + a suggested package/price to post.

**Data:** reuse `inbound_messages`; optional `demand_signals` rollup.
**Surface:** owner-brief weekly section + portal Reports "Demand radar" card.
**Safety:** read-only intelligence; no sends.
**Meta edge:** Meta answers one chat; **nobody briefs the owner on the aggregate.** New category.
**Effort:** M.

---

## 4 · EYO Cashflow — the WhatsApp CFO

**What:** forecast the owner's week — likely collections, at-risk naira in stalled
chats, who to nudge.

**Reuses:** `money_leak` (confirmed + pipeline), `receipt_matches` (inflow history), `cash_signals`, `copilot`, `outcome_learning` (close-rate).

**New pieces:**
- `services/cashflow.py` → `forecast(client, horizon_days=7) -> {expected_ngn, at_risk_ngn, drivers[], nudge_targets[]}`. Blend confirmed-owed + hot pipeline + historical close-rate + deposit cadence.

**Surface:** portal Money "This week" card + owner-brief Monday line.
**Safety:** clearly labelled estimate (like the savings line).
**Meta edge:** a forecast no messaging tool offers; owner-side CFO-lite.
**Effort:** M (mostly composition of existing signals).

---

## 5 · EYO Referral — word-of-mouth engine

**What:** after a happy close, ask for a referral/review at the right moment,
track it, and work the referred contact.

**Reuses:** `outcome_learning` (detect win), HITL/drafter, memory, `/hi/{slug}` link tracking.

**New pieces:**
- `services/referral.py` → trigger on confirmed close + positive sentiment → queue a referral-ask draft (HITL) at +N h; mint a trackable referral link/code; on inbound from a referred contact, attribute + start them warm.
- Data: `referrals` collection `{client, referrer_phone, code, referred_phone?, status, reward?}`.

**Surface:** portal Reports "Referrals" + owner-brief "X referrals in flight".
**Safety:** HITL on the ask; respect opt-out.
**Meta edge:** closes the money → reputation → money loop; Meta serves chats, not growth loops.
**Effort:** M.

---

## Why these, now (the Meta tie-in)

Meta normalised generic WhatsApp AI and raised buyer expectations overnight — but
its agent is horizontal, stateless, and English-generic. Each invention above is
**one-business-deep** and money-touching: exactly the lane Meta structurally
cannot follow us into (see `INVESTOR.md §6.5`). Building these widens the gap
while Meta widens the top of the funnel for us.
