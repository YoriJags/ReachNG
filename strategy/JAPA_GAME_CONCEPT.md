# JAPA — Crash Game Concept (Separate Venture, Not ReachNG)

**Status:** SHELVED as flagship (2026-06-11) — founder wants a new primitive, not an Aviator derivative. Flagship is now `WAHALA_GAME_CONCEPT.md`. JAPA remains a viable second shelf title.
**Origin:** Post-AGE 2026 AfriPitch win. Founder has direct operator plugs (Bet9ja-tier reachable via AGE network).
**One-liner for operators:** *"The next Aviator, built for Africa first — with a PvP layer Aviator can't copy and a game mode where the house mathematically cannot lose."*

---

## 1. Why a new crash game can win now

- Aviator (Spribe, 2019) proved the category: ~42% of African online casino GGR flows through crash-style games on major operators. Its UX has barely changed since launch.
- Every aggregator (SoftSwiss, EveryMatrix, Pragmatic hub) now has a "crash" shelf and operators actively shop for differentiated titles — but 200+ clones offer nothing new, so shelf space is open for a real invention.
- Spribe is a **B2B game supplier**, not the house. Operators (SportyBet, Bet9ja, 1xBet) hold player funds and pay Spribe ~10–15% of GGR. That is the business we are building: certified game studio → aggregator/direct deals → revenue share. Software economics, no betting risk capital.
- Founder's unfair advantage: AGE-validated credibility + warm operator relationships = the distribution that kills most studios.

## 2. The name is the mechanic

The cash-out button says **JAPA**. The multiplier climbs, wahala approaches, you japa before it catches you. Zero player education needed in Nigeria; exportable as an exotic brand elsewhere (per-market reskins possible — same certified engine).

Visual theme: night-time Lagos run — okada weaving through traffic, curve = speed. Bust animation = "Wahala caught you." Tone is comedy, not menace.

## 3. Core game (conservative where regulators look)

Standard provably-fair crash, industry-canonical so GLI-19 auditors certify it without novelty risk:

- Server seed chain: pre-committed hash chain (publish terminal hash; each round reveals previous seed — verifiable backwards).
- Crash point: `h = first 52 bits of HMAC-SHA256(serverSeed, clientSeedMix + roundNonce)`, mapped so that `P(crash ≥ m) = (1 − e) / m` for multiplier `m`, with base curve edge `e` (tunable, see §4 math note).
- Round cadence: 5s stake window → ride (median ~10s) → 3s settle. Fast, but with mandatory operator-side reality checks and stake/loss limits (see §8).
- All payouts in operator wallet via standard RGS seamless-wallet API. We never hold player funds.

## 4. Invention #1 — The Wahala Pot (the moat)

**Mechanic:** When a player busts, a fixed fraction **β** of their stake (target β = 40–50%) visibly drops into the on-screen **Wahala Pot**. At round end the pot pays out to survivors who japa'd, weighted by boldness:

```
payout_i = W × (s_i · m_i^α) / Σ_j (s_j · m_j^α)
```

- `W` = current Wahala Pot, `s_i` = stake, `m_i` = exit multiplier, `α` ≈ 1.5 rewards late exits superlinearly.
- **Rollover:** if no one survives (everyone busts — common in small rounds, rare in big ones), W rolls to the next round. Pots visibly swell across rounds → appointment gameplay ("Mega Japa" rounds when W crosses a threshold, promotable by the operator).

**Why Aviator can't copy it:** their certified math pays each player independently against the house. Wahala Pot makes payouts *interdependent* — a different game class requiring recertification and a redesigned client. First mover holds this for 12–24 months minimum.

**Solvency / RTP math note:** redistributing busted stakes raises total RTP, so the base curve edge `e` is set higher (≈6–7%) such that **combined RTP (base + Wahala redistribution) lands at 96–97%** with house GGR ≈3–4% guaranteed in expectation. Exact `e`, `β`, `α` come from Monte Carlo tuning (deliverable of the demo build — we ship the simulation notebook with the cert package).

**Psychology shift:** Aviator is me-vs-house (cynical: "house always wins"). JAPA is me-vs-the-timid: busted players' money goes to *bold players*, on screen, every round. It's a contest, not a slot.

## 5. Invention #2 — Squad Rooms (esusu mode; house cannot lose)

Private rooms: friends stake into one pot, ride the same curve, last-to-japa takes the pot (or top-3 split, room-configurable). Operator takes a flat **5% rake** of the pot.

- **Zero house variance.** Pure rake — guaranteed margin every round, no exposure to a lucky whale. This is the strongest single line in the operator pitch.
- Culturally native: digitizes the esusu/ajo social pooling behavior that already exists.
- No crash game in market has private PvP rooms. Drives retention (friends summon friends) and organic acquisition.

## 6. Invention #3 — WhatsApp-native replay clips

Every notable moment (big japa, brutal bust, Mega Japa win) auto-renders a ~10s vertical clip: pot, curve, exit point, JAPA branding. One tap → WhatsApp status / TikTok.

- Aviator's organic growth came from hand-made streamer clips; JAPA manufactures them at the moment of peak emotion.
- In Nigeria, WhatsApp status *is* the distribution channel. Every winner becomes a marketer.
- Spectator mode + streamer overlay API ships with v1 (Twitch/TikTok Live ready).

## 7. Operator pitch (the three slides that matter)

1. **Differentiation:** the only crash title with an interdependent PvP pot — players watch other players' losses become their upside. Not a 201st clone.
2. **Economics:** base game ≈3–4% guaranteed GGR margin (certified RTP); Squad Rooms are pure rake with zero variance; rollover pots are a built-in, self-funding promo engine (no operator bonus budget burned).
3. **Growth:** auto-clip system turns every win into WhatsApp distribution; Mega Japa rounds are a recurring marketing beat.

Deal shape: standard supplier rev-share 10–15% of GGR via aggregator, or direct integration pilot with one plug operator (faster, better terms, exclusivity window in exchange for launch promotion).

## 8. Regulatory & certification path (the real critical path)

| Step | What | Cost / time (est.) |
|---|---|---|
| 1 | Entity setup (separate company — NOT ReachNG) | weeks |
| 2 | Monte Carlo math pack + RNG documentation | with demo build |
| 3 | GLI-19 / BMM RNG + game logic certification | $15–50k, 2–4 mo |
| 4 | Nigeria: ride on operator's NLRC/state license as certified supplier; confirm supplier-permit requirements per state (Lagos LSLGA) | legal counsel |
| 5 | Curaçao/Malta B2B supplier license for pan-African + global ops | $20–60k, 3–6 mo |
| 6 | Nevada (Vegas) manufacturer/distributor license | Year 3 goal — high capital, multi-year probity. Not in v1 plan. |

**Responsible gambling is built in, not bolted on:** stake limits, session loss limits, reality-check prompts, self-exclusion hooks via operator API. Operators and regulators require it; shipping it natively shortens every compliance review. Design principle: JAPA competes on *contest and spectacle*, not on dark patterns — that is also what passes certification.

## 9. Demo plan (what we build before any license)

A **play-money multiplayer demo** is legal everywhere and is what the plugs need to see. Target: pitch-ready in 4–6 weeks of focused build.

- **Client:** HTML5 (PixiJS/Canvas), mobile-first, 3G-tolerant (<2MB initial load, reconnect-safe websockets — non-negotiable for the Nigerian market).
- **Server:** authoritative game server, WebSocket rounds, real provably-fair seed chain (the actual cert-track implementation, not a mock), play-money wallets.
- **Includes:** live Wahala Pot + rollover, one Squad Room, auto-clip prototype, public fairness-verifier page.
- **Demo liquidity:** clearly-labeled demo bots to make rooms feel alive in a pitch — labeled, never deployed in any real-money build.
- **Sim notebook:** Monte Carlo of e/β/α showing combined RTP — doubles as the start of the GLI math pack.

## 10. Relationship to ReachNG

Separate venture, separate entity, separate repo when build starts. Current ReachNG focus (first Lagos EstateOS/EYO client) is unchanged. This doc exists so the thinking is captured and pitch-ready when founder activates the AGE plugs.

---
*Drafted 2026-06-11.*
