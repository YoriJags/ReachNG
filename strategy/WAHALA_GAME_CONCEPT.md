# WAHALA — The Minority-Game Arena (Flagship Concept)

**Status:** Flagship venture concept. Supersedes JAPA (crash variant — shelved, see `JAPA_GAME_CONCEPT.md`) after founder call: must be a new primitive, not an Aviator derivative.
**One-liner (player):** *"Wahala follows the crowd. Pick a door. Stand where they're not — but so does everyone else."*
**One-liner (operator):** *"A 90-second live elimination arena with real players that manufactures its own in-play betting markets, 24/7, zero rights fees — plus a parimutuel pot where the house carries zero variance."*

---

## 1. The primitive (what has never been done)

Every certified casino game has **house-fixed probabilities**. WAHALA's probabilities are **created live by the players** — the first productization of the *minority game* (El Farol problem) as real-money gambling:

- Arena of 50–500 players, flat entry stake, 5 elimination rounds, ~90 seconds total.
- Each round: pick one of **3 doors**. Live counters show how many players stand behind each door.
- The eliminated ("hot") door is drawn by provably-fair RNG **weighted by crowd size**:

```
P(door d is hot) = (N_d + s) / (N + 3s)
```

  where `N_d` = players behind door d, `N` = total alive, `s` = smoothing constant so empty doors keep residual danger (prevents degenerate certainty).
- **Danger follows the crowd.** The lonely door is safest — but everyone knows it, so it can't stay lonely. No dominant strategy exists; the equilibrium is mixed. The game is psychology with chance as executioner, and it is **self-balancing by construction** (any popular "system" raises the danger of the doors it recommends).
- **Risk premium:** survivors are weighted by the danger they survived. Per-round weight factor for choosing door d: `w = (N_d / N)^γ` normalized (γ ≈ 1.2–1.6, tuned by simulation). Surviving a crowded door pays more than hiding behind an empty one. Compounded over 5 rounds → top-heavy, dramatic payouts.
- **The Blackout:** door counters freeze/blur for the final 3 seconds of each pick window. Kills last-second sniping; doubles as the signature dramatic beat.
- Final survivors split the pot: `payout_i = (Pot − rake) × W_i / Σ W_j` where `W_i = Π w_i,round`. Parimutuel → solvent by construction.

**Not-Aviator checklist:** no multiplier curve, no cash-out timing, no house-banked core bet. Tournament loop, crowd-reading psychology, endogenous probabilities. A different genus, not a different skin.

## 2. Engine two — the spectator sportsbook (the operator hook)

On elimination, one tap converts the player into a **bettor on the arena they just left**:

- Which door blows next (odds derived live from the actual crowd distribution — self-generating odds feed)
- Over/under on survivors per round and at final
- Named-player survival (player cards/avatars; follow, back, or bet against a rival)

Outside spectators can watch and bet without ever entering an arena.

Strategic read on the buyers: SportyBet/Bet9ja are **sportsbooks** — in-play betting on live events is their DNA and football data rights are a major cost line. WAHALA gives them a live event with real humans and real drama every 90 seconds, around the clock, **with zero rights fees**. Virtual sports proved the appetite; virtuals are watch-only cartoons. No product in market has real players *inside* the event.

## 3. House economics (two revenue lines per 90 seconds)

| Line | Model | House risk |
|---|---|---|
| Arena pot | Parimutuel, 4–6% rake | **Zero variance** — guaranteed margin, solvent by construction |
| Spectator markets | House-banked fixed odds, certified margin (or pooled variant) | Standard certified-edge exposure, operator-configurable |

Supplier deal shape: rev-share 10–15% of GGR via aggregator or direct operator pilot (preferred: exclusivity window with a plug operator in exchange for launch promotion).

## 4. Social & cultural layer

- **Name:** WAHALA — instantly meaningful in Nigeria, exotic and pronounceable in Vegas ("trouble follows the crowd"). Alt name if needed: LASTMAN.
- Aesthetic: Nigerian street-festival / danfo-park energy. Elimination-gameshow genre (Takeshi's Castle lineage) — **no Squid Game IP echoes** in visuals or naming.
- Arena identity: rep your city (Lagos vs PH vs Abuja arenas), preset pidgin trash-talk stickers (moderation-safe, no free text).
- Auto-generated vertical clips: final-door blackouts, lone-survivor moments, "backed my enemy and won" spectator wins → one-tap WhatsApp status share.
- Follow/rivalry graph: persistent player handles, head-to-head records → grudges → retention.

## 4b. The Masquerade — thrill & resonance layer (what makes it felt, not just clever)

The hot door is never "announced." **The wahala is a masquerade, and it walks.**

- After the blackout, a masquerade emerges and stalks the three doors for 6–8 seconds — feints toward one, passes, doubles back, strikes. The outcome is already cryptographically fixed at blackout (provably fair; the walk is deterministic theatre rendered from the committed result), but the *approach* is the game's rising curve: sustained, personal dread — it is coming toward **your** door. This gives a discrete game the continuous heart-rate tension that made Aviator physical.
- Cultural ground truth: every Nigerian has the body-memory of running from a masquerade — and when masquerade enters the street, hiding in the crowd doesn't save you. The core mechanic ("danger follows the crowd") is a lived national experience, not a rule to learn.
- **Audio is half the product:** talking-drum tempo rising with the approach, crowd roar scaled to live player count, dead silence at blackout, "GBOZA" on the strike. (Aviator's tension is substantially audio; budget sound design as a first-class workstream.)
- **Pre-installed language:** "Wahala for who no run" — Nigeria already memes in wahala. Name, threat, catchphrase and trash talk are one word people use daily; players explain the game to each other in one pidgin sentence.
- **Near-miss engine:** "the masquerade passed my door" every 90 seconds — the most retold gambling story there is, auto-rendered as a WhatsApp clip. Plus the organic screenshot flex: "I was the ONLY one behind door 2."
- Vegas translation: masquerade → "the Hunter"/Reaper house character. Chase mechanic is universal; only the costume localizes.

### Talk-of-the-town program (engineered, not hoped for)

1. **Friday Night Mega Arena** — one scheduled 10,000-player arena, operator-seeded pot, all-week countdown. Appointment viewing; winners become minor celebrities.
2. **Celebrity arenas** — a celebrity plays *inside* an arena while six figures of spectators bet on his door-by-door survival. No existing casino game can host this; one celeb arena = a national Twitter night for the price of an appearance fee.
3. **Streamer-native** — chat votes the door, streamer obeys or defies; the masquerade walk is a guaranteed clip every round. Built-in overlay API.
4. **Area rep** — Lagos vs PH vs Abuja arenas; survivors carry area badges; rivalry is free distribution.

## 5. Fairness & certification

- Hot-door draw: pre-committed server seed chain (publish terminal hash; reveal backwards), `HMAC-SHA256(serverSeed, roundNonce)` mapped through the published crowd-weighted distribution. Weighted provably-fair draws are established cert territory (jackpot wheels); the novelty is *where the weights come from*, and the weights (final locked crowd counts) are published per round → fully player-verifiable.
- Choice lock: server-authoritative at blackout start; locked distribution published post-round.
- Anti-collusion note: collusion cannot tilt the draw in a colluder's favor — crowding a door *raises* its danger; spreading thin lowers individual shares. The mechanic punishes coordination naturally. (Formal analysis goes in the cert math pack.)
- Combined payout structure tuned by Monte Carlo over `s`, `γ`, rake, arena sizes → target effective player return 94–96% on arena play; spectator markets carry independent certified RTP. Simulation notebook is a demo-phase deliverable and the seed of the GLI-19 math pack.
- Responsible gambling native: stake/loss limits, session reality checks, self-exclusion via operator API. The game competes on contest and spectacle, not dark patterns — that is also what passes certification.

## 6. Cold start & liquidity

- Scheduled arena times + continuous arenas at peak.
- Operator-seeded guaranteed pots as launch promos (their marketing budget, our mechanic).
- **Cross-operator shared arenas** through our central game server (poker-network model): every operator's players enter the same arenas → instant liquidity, and the network effect makes the supplier (us) progressively harder to displace.
- Minimum-viable arena: 50 players; below threshold, entry rolls to next arena (never bots in real-money play).

## 7. Demo plan (pre-license, play-money — what the plugs see)

Target: pitch-ready in ~6 weeks of focused build.

- HTML5 client (PixiJS), mobile-first, <2MB initial load, reconnect-safe websockets (3G-tolerant — non-negotiable).
- Authoritative arena server: rounds, blackout lock, real provably-fair seed chain (cert-track implementation, not a mock).
- One full arena loop with live door counters, blackout, elimination reveal, payout ladder.
- Eliminated-to-spectator flow with two live side markets (next hot door, survivor over/under).
- Auto-clip prototype + public fairness-verifier page.
- Monte Carlo notebook (`s`, `γ`, rake sweeps) proving payout targets.
- Demo arenas filled with clearly-labeled bots for pitch liveliness — labeled, never in any real-money build.

## 8. Regulatory path (unchanged from JAPA doc, summarized)

GLI-19/BMM certification ($15–50k, 2–4 mo) → ride operator NLRC/state licenses as certified supplier (Lagos LSLGA counsel check) → Curaçao/Malta B2B for pan-African → Nevada manufacturer license as a Year-3 goal. Separate entity from ReachNG before any operator conversation goes to paper.

## 9. Relationship to ReachNG

Separate venture, separate entity, separate repo at build start. ReachNG focus (first Lagos EstateOS/EYO client) unchanged. Doc parked here so it is pitch-ready when founder activates AGE plugs.

---
*Drafted 2026-06-11. Supersedes JAPA as flagship; JAPA remains a viable shelf title.*
