# ReachNG — Unit Economics

Honest, operator-grade breakdown of what one paying client actually costs us to run, and what the existing admin dashboard sees vs. what it misses.

Last updated: 2026-05-20 (pre-pricing session)

---

## 1 · Cost categories

We split costs into three buckets:

| Bucket | Scales with | Example |
|---|---|---|
| **Per-call (metered)** | Each AI call a client triggers | Whisper transcribe, Haiku draft, Vision receipt |
| **Per-client fixed** | Each connected client, regardless of volume | Unipile per-number, Meta WhatsApp messaging fee, Resend share |
| **Platform fixed** | Total system, not per client | Railway hosting, Mongo Atlas, PostHog, domain |

The meter (`services/usage_meter.py`) tracks bucket 1 only. Buckets 2 and 3 need manual attribution — see §5.

---

## 2 · Per-call costs (the meter sees these)

Rates currently encoded in `services/usage_meter.py::FEATURE_COSTS`:

| Feature | ₦/call | Underlying call | What triggers it |
|---|---:|---|---|
| `voice` | 8 | OpenAI Whisper (~30–90s audio) | Every inbound voice note |
| `receipt` | 10 | Anthropic Haiku 4.5 vision | Every inbound image (receipt screenshot) |
| `classifier` | 2 | Haiku, ~200-400 tok | Every inbound text classified for emotion / intent |
| `drafter` | 4 | Haiku, ~400-700 tok | Every reply EYO drafts (HITL queue) |
| `memory` | 3 | Haiku, structured extraction | Every inbound that bumps the client memory layer |
| `copilot` | 8 | Haiku planner + narrator | Each owner Co-Pilot question |

**These are anchors, not contracts.** They were set conservatively before live data. Reconcile against actual API invoices monthly via `services/usage_meter.py` ledger.

### Reality-check against vendor pricing (2026-05 Nigerian rates)

- **OpenAI Whisper:** $0.006/minute audio = ₦9.60/min @ ₦1600/USD. Most voice notes ≤ 1 min → ₦5-10. **Ledger rate of ₦8 ≈ realistic.**
- **Haiku 4.5:** $0.80 input / $4 output per million tokens. A 600-token draft (350 in / 250 out) = $0.0013 = ₦2.10. **Ledger rate of ₦4 ≈ 1.9× safety buffer.**
- **Haiku 4.5 vision (receipt):** ~1500 image tokens + 300 output = ~$0.0024 = ₦3.80. **Ledger rate of ₦10 is generous** (justified — vision retries on poor receipts).
- **Memory extraction:** ~300 tok in / 100 tok out = ₦1.20. Ledger ₦3, buffered.
- **Co-pilot:** Two Haiku calls (planner + narrator). ~₦5 actual. Ledger ₦8 buffered.

Net: the ledger over-estimates by ~30–50% versus raw API cost. That buffer absorbs retries, error paths, and FX swings. **Don't tune down until 60+ days of real data confirms it.**

---

## 3 · Per-call cost by client usage profile

Three realistic Lagos/Abuja archetypes. Numbers are **monthly counts** of each feature event.

### Profile A — Light (small restaurant, beauty salon, single agent)

| Feature | Count/mo | ₦/call | Total ₦/mo |
|---|---:|---:|---:|
| voice | 60 | 8 | 480 |
| receipt | 30 | 10 | 300 |
| classifier | 300 | 2 | 600 |
| drafter | 200 | 4 | 800 |
| memory | 100 | 3 | 300 |
| copilot | 5 | 8 | 40 |
| **Per-call total** | | | **₦2,520/mo** |

### Profile B — Medium (premium hospitality, mid-size clinic, established RE agency)

| Feature | Count/mo | ₦/call | Total ₦/mo |
|---|---:|---:|---:|
| voice | 200 | 8 | 1,600 |
| receipt | 80 | 10 | 800 |
| classifier | 900 | 2 | 1,800 |
| drafter | 600 | 4 | 2,400 |
| memory | 300 | 3 | 900 |
| copilot | 15 | 8 | 120 |
| **Per-call total** | | | **₦7,620/mo** |

### Profile C — Heavy (high-volume clinic, multi-location restaurant, busy agency)

| Feature | Count/mo | ₦/call | Total ₦/mo |
|---|---:|---:|---:|
| voice | 500 | 8 | 4,000 |
| receipt | 150 | 10 | 1,500 |
| classifier | 2,500 | 2 | 5,000 |
| drafter | 1,500 | 4 | 6,000 |
| memory | 700 | 3 | 2,100 |
| copilot | 30 | 8 | 240 |
| **Per-call total** | | | **₦18,840/mo** |

---

## 4 · Per-client fixed costs (NOT in the meter today)

These attach to a client by the act of connecting them, even if they barely use the system. **This is where pricing surprises live.**

| Line item | Cost basis | Per-client ₦/mo |
|---|---|---:|
| **Unipile WhatsApp account** | Real published tiered pricing: $55/mo flat for first 10 accounts, then $5.5/account (11-50), $5 (51-200), $4.5 (201-1k), $4 (1k-5k), $3.5 (5k+). Effective: ₦7,400-8,800 per client across all scales. | ~₦8,800 at 10 clients |
| **Meta Cloud API messaging fee** | First 1,000 service conversations/mo free; then ~$0.0094/conversation for Nigeria utility tier | 0 to ~₦3,000 |
| **Resend transactional email** | Shared $20/mo plan ÷ ~20 clients = ~$1 attributable | ~₦1,600 |
| **MongoDB Atlas share** | Currently on free tier M0 (512MB). ₦0 today. Move to M10 (~$57/mo) at ~10-12 clients = ~₦9,100 then. | ~₦0 (today) |
| **Anthropic + OpenAI floor** | API key flat fees ≈ $0 once usage-based; only fixed minimums during low usage | 0 |
| **Estimated per-client fixed** | | **~₦12,000/mo** (today, Mongo free, 10-client scale) |

**Critical:** the Unipile per-account fee dominates. ₦24k/client is the floor before EYO has done a single Haiku call.

### Alternative: Meta Cloud API direct (skip Unipile)

We have Meta Cloud integration coded too. Cost shifts:

- Unipile fee → **₦0**
- Meta conversation fees scale with volume: utility template messages ~₦15 each, marketing ~₦70 each
- Up to 1,000 free service conversations/mo means most clients pay near-zero Meta fees

Per-client fixed via Meta direct: **~₦6,000/mo** (Resend + Mongo only).

**Strategic implication:** offer clients on cheaper plans (Starter) Meta direct, while higher-tier (Growth/Scale) get Unipile for hosted-auth convenience. Cuts Starter fixed cost by ~75%.

---

## 5 · Platform fixed costs (NOT per client)

These don't attribute per-client, but they need to be paid by *somebody's* margin.

| Line item | ₦/mo | Notes |
|---|---:|---|
| Railway hosting | ~₦16,000 ($10) | Single service, scales modestly |
| Mongo Atlas M0 (free) | ~₦0 today | On free tier; switches to M10 (~₦91k) around 10-12 clients |
| Resend Pro | ~₦32,000 ($20) | Shared (counted partially above) |
| PostHog | 0 | Free tier sufficient until 1M events/mo |
| **OpenAI Whisper budget cap** | **~₦240,000 ($150)** | Pre-funded monthly ceiling for voice transcription. Bursts above this require operator approval. Sized for ~25k minutes of inbound audio/mo (covers a full Tier-0 + Tier-1 cohort with comfortable headroom). |
| **Anthropic Claude API budget cap** | **~₦160,000 ($100)** | Pre-funded monthly ceiling for production drafts (Haiku 4.5 + occasional Vision OCR). Sized for ~3.5M tokens/mo at current per-token rates. Caller-side rate limits in `services/usage_meter.py` enforce the ceiling per client. |
| **Claude Pro subscription (founder tooling)** | **~₦32,000 ($20)** | The Pro subscription Yori uses to build, draft, plan, debug. Powers everything Claude Code touches. Upgrades to Max 5× (~₦160k) likely once parallel sessions matter, Max 20× (~₦320k) once team grows. |
| Domain + SSL | ~₦5,000/mo amortised | reachng.ng renewal |
| **Platform fixed total (today)** | **~₦485,000/mo** | At 10 clients = ~₦48,500/client. At 25 clients = ~₦19,400/client. Jumps with Mongo M10 (~+₦91k) around 10-12 clients. |

**Claude Pro → Max trajectory:**
- 0-15 clients: Pro is fine (~₦32k/mo)
- 15-50 clients: Max 5× (~₦160k/mo) — operator runs parallel Claude Code sessions, builds faster
- 50+ clients: Max 20× (~₦320k/mo) — multiple ops team members on Claude
- Even at Max 20× ÷ 100 clients = ₦3,200/client overhead. Negligible at scale.

**API budget caps — why pre-fund vs metered:**
- Predictable line items investors can underwrite. No "AI costs went 4× this month" surprises.
- Hard ceilings on usage_meter.py protect runway during a viral spike or scrape attack.
- If we routinely hit the ceiling, that's a *good* problem — raise the cap and reprice.

Allocate platform fixed across active clients when computing true margin.

---

## 5.5 · Growth / marketing budget (separate from COGS)

This is **not** cost-of-goods-sold. It's the acquisition spend that compounds into paying clients. Tracked separately so unit economics stay honest.

| Line item | ₦/mo | Notes |
|---|---:|---|
| **Meta Ads (Facebook + Instagram)** | ~₦320,000 ($200) | Lagos-targeted lookalike + retargeting campaigns. Vertical-specific creative per SCENE_PACK. CAC target ≤ 30% of first month's MRR. |
| **Google Ads** | ~₦240,000 ($150) | Branded + 5-6 high-intent terms ("WhatsApp AI assistant Lagos", "auto-reply customers Nigeria"). Mostly defensive once SEO ranks. |
| **SEO tooling (Ahrefs / SEMrush starter)** | ~₦160,000 ($99) | Keyword tracking, backlink audit, competitor monitoring (johahq + any new Lagos rivals). |
| **LinkedIn Sales Navigator (founder outreach)** | ~₦128,000 ($79) | For Yori's direct outreach to luxury RE / legal / clinic founders. |
| **Content production (occasional freelance)** | ~₦200,000 | One case-study write-up or video edit per month once first paid client lands. |
| **Apify (SDR funnel discovery)** | ~₦16,000 ($10) | Our own internal lead-discovery for the Prospect OS funnel. Was previously double-counted under platform fixed. |
| **Marketing total (today)** | **~₦1,064,000/mo (~$665)** | Roughly $0.66k/mo at Year 1 ramp. Scales to $1.5-2k/mo by Month 6 if early signals are strong. |

**Acquisition math at this spend:**
- Target blended CAC ≤ ₦300,000 (~ 2× a Starter month) — every paid client recovers CAC inside 60 days.
- At 5 net-new clients/mo, blended CAC = ₦213k. Within target.
- At 2 net-new clients/mo, blended CAC = ₦532k. Outside target — pause Ads, lean into founder outreach + organic.
- Re-evaluate spend split monthly. Cut what doesn't pay back; double the channel that does.

---

## 6 · Total cost per client per month

Combining sections 3 + 4 + 5 (allocating platform fixed across 10 clients):

| Profile | Per-call | Per-client fixed (Unipile) | Per-client fixed (Meta direct) | + Platform share | **TOTAL (Unipile)** | **TOTAL (Meta)** |
|---|---:|---:|---:|---:|---:|---:|
| Light  | 2,520 | 30,160 | 6,160 | 15,200 | **~₦47,880/mo** | **~₦23,880/mo** |
| Medium | 7,620 | 30,160 | 6,160 | 15,200 | **~₦52,980/mo** | **~₦28,980/mo** |
| Heavy  | 18,840 | 33,160 | 9,160 | 15,200 | **~₦67,200/mo** | **~₦43,200/mo** |

### Margin at proposed pricing (current PRODUCTS.md ladder)

| Plan | Price/mo | Light client (Unipile) | Light client (Meta) | Medium (Unipile) | Heavy (Unipile) |
|---|---:|---:|---:|---:|---:|
| Starter ₦80k | 80,000 | +₦32,120 (40%) | **+₦56,120 (70%)** | +₦27,020 (34%) | +₦12,800 (16%) |
| Growth ₦150k | 150,000 | +₦102,120 (68%) | +₦126,120 (84%) | **+₦97,020 (65%)** | +₦82,800 (55%) |
| Scale ₦300k | 300,000 | +₦252,120 (84%) | +₦276,120 (92%) | +₦247,020 (82%) | **+₦232,800 (78%)** |

Read: **Starter via Unipile on a light client = 40% margin. Tight.** Same plan via Meta direct = 70% margin. **This is why we have to route Starter clients through Meta Cloud direct, not Unipile.**

Growth and Scale absorb Unipile fine. Heavy clients on Starter are unprofitable to dangerous (16% margin doesn't cover surprise spikes).

### Decision matrix from this table

- **Move Starter to Meta Cloud API only.** No Unipile pairing on Starter. Healthy 70% margin.
- **Growth gets Unipile.** 65% margin on a medium client is the sweet spot.
- **Scale gets Unipile + priority + Co-Pilot extras.** 78–82% margin on heavy. Real money per client.
- **Cap Starter usage** to Light profile (~₦2,500/mo per-call). If a client trends Medium on Starter, auto-prompt upgrade ("you're using Growth-level volume, here's what changes").

---

## 7 · The runaway / abuse cases

A single rogue client can torch margin. The meter has anti-runaway already; here's what protects us:

| Feature | Per-minute hard cap (in code) | Effect of cap |
|---|---:|---|
| voice | 20 calls/min | Max ₦9,600/hour on Whisper |
| receipt | 20 calls/min | Max ₦12,000/hour on vision |
| classifier | 60 calls/min | Max ₦7,200/hour |
| drafter | 60 calls/min | Max ₦14,400/hour |
| memory | 60 calls/min | Max ₦10,800/hour |
| copilot | 15 calls/min | Max ₦7,200/hour |

These caps are short-window; sustained abuse over hours is what the daily/monthly alert layer needs to catch. **Recommended addition:** flag any client whose 7-day rolling cost exceeds 2× the cost-of-tier baseline, surface on admin dashboard as `at_risk`.

---

## 8 · What the admin dashboard sees today

Already shipped (`templates/dashboard.html` line ~2400, `api/billing.py`):

- Per-client table: revenue, API cost MTD, margin %, top spend feature, `at_risk` flag
- Cohort totals: platform-wide revenue, cost, margin, client count
- Per-client drill-in via `/api/v1/admin/billing/{client_id}` showing usage by feature

What this view is missing (the gap to close before first paid client):

1. **Per-client fixed costs not attributed.** The table shows API costs only. Unipile, Resend share, Mongo share are zero in the UI. Real margin is **always lower** than shown.
2. **No platform-fixed allocation.** A "platform overhead" line per client isn't included.
3. **No trend chart.** Just MTD totals. We need 30/60/90-day series to spot rising usage before it becomes a margin emergency.
4. **No usage-by-profile classification.** We can compute whether a Starter client is exhibiting Medium/Heavy usage. Auto-prompt upgrade.
5. **No runaway alerting.** `at_risk` flag exists but only logs; no Slack / WhatsApp / email push to the operator.

## 9 · Recommended dashboard upgrade (Phase next)

Order of priority for the build:

1. **Attribute per-client fixed costs** in the billing query so margin % reflects reality. Add a `fixed_cost_ngn` field on `clients` doc (default ₦24k Unipile / ₦6k Meta) and add to the total. *(1 hour)*
2. **Allocate platform-fixed** by dividing the manually-entered `platform_overhead_ngn` (current ₦152k) across active client count. *(30 min)*
3. **Profile classifier** that reads usage and labels each client `light` / `medium` / `heavy`. Surface on the row so we can spot upgrade prompts. *(1 hour)*
4. **30-day trend chart** per client (cost line + revenue line). Tiny inline sparkline in the row. *(2 hours)*
5. **Runaway push alert** when 7-day rolling cost exceeds 2× tier baseline → Slack webhook + owner WhatsApp via `OWNER_WHATSAPP` env. *(1 hour)*

Total: **~5.5 hours** to make the dashboard production-grade for margin defense.

---

## 10 · The numbers to lock in the pricing session

When we sit down for pricing today, the only inputs you need to bring are:

1. Your **target gross margin %** per tier (industry norm for SaaS: Starter 50%, Growth 70%, Scale 80%)
2. Your **floor instinct** — what would feel wrong to charge less than? (Anchors the bottom)
3. Your **ceiling instinct** — what would make a premium Lagos owner say "that's the price of a junior staffer's monthly salary, no thanks"? (Anchors the top)

Everything else (cost per profile, margin at price, breakeven volume) is in this doc.

**My recommendation as a starting point:**
- **Starter ₦80k** → keep, route via Meta Cloud only. 70% margin on a light client. Healthy.
- **Growth ₦150k** → keep. 65% margin on medium client via Unipile. Sweet spot.
- **Scale ₦300k** → keep. 78%+ margin even on heavy clients.

Then tune from there based on your reads.
