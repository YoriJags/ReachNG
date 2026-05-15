# Security & Scale — ReachNG

**Last reviewed: 2026-05-15.** Authoritative answer for "is this insecure?" / "will this scale?" / "why not Supabase?" Update when the lifecycle thresholds below get hit.

---

## Security — is it actually insecure?

**No.** HTTP Basic Auth (admin) + unguessable portal tokens (clients) is **not** insecure when:

- All traffic runs over HTTPS — Railway forces it
- Tokens have enough entropy — ours are 24 bytes / ~10⁵⁷ possibilities = unguessable
- Secrets aren't in source code — they're in Railway env vars, encrypted at rest

This is the same model **Notion share links, Figma share links, Calendly bookings, and Linear shared boards** use. It's called "unguessable URL" auth and it's industry-standard for the share-a-link pattern.

### Already doing well

- **HITL gate** — no AI can send without owner approval. Kills 90% of AI-product security incidents at the architecture level (`tools/hitl.py::queue_draft()` is the only send initiator)
- **Per-client scope locking** in `services/client_memory.py` + `services/scorecard.py`. `MemoryScopeViolationError` raised on any cross-client access
- **Audit log** on every memory read/write
- **Nightly isolation self-test** — `tests/test_isolation.py` plus 03:00 Lagos scheduler job persisting to `isolation_audits`
- **No PII in structlog** — enforced by CLAUDE.md rule
- **TLS everywhere** — Mongo Atlas TLS, Railway TLS, encrypted env vars

### Hardening to add before 100 paying clients (lifecycle, not crisis)

- Token expiry + 90-day rotation
- Login attempt rate-limiting on the admin dashboard (brute-force defence)
- Full audit log on every dashboard login (partial today)
- CSP / security headers middleware
- Optional 2FA for admin
- Mongo backup automation

None of these are "we have a vulnerability" — they're "we've matured past 10 clients, time to harden." Standard SaaS lifecycle.

---

## Scalability — can the current architecture scale?

**Yes, well past where we'll need to worry about it.** The bottleneck order, hit in this sequence:

1. **Anthropic API rate limits** — Tier-3 ≈ 50K req/min, Tier-4 uncapped. Hit first. Easy upgrade.
2. **Unipile per-account limits** — each client's WhatsApp number has its own. Already daily-capped in code.
3. **OpenAI Whisper limits** — easily managed.
4. **MongoDB Atlas** — millions of docs per collection is fine.

Our Mongo patterns all fit the engine natively:
- Indexed `{client_id, contact_phone}` lookups — Mongo's bread and butter
- Embedded thread arrays in `closer_leads` — better in Mongo than Postgres
- Append-only audit logs — Mongo handles this fine

**You'll outgrow the Anthropic budget long before Mongo.**

The real scale ceiling is **humans on the team to onboard clients well**. That's why the waitlist exists — it gates volume to what we can hand-onboard.

---

## Why not Supabase

Deliberate architectural choice, not a gap.

- **Auth** — HTTP Basic + portal tokens. Simpler, fewer moving parts, easier audit.
- **Realtime** — not needed. HITL is a polling/scheduler pattern; push notifications go via WhatsApp.
- **File storage** — not needed. Unipile and Meta host all media; we just read and process.

Switching to Supabase to gain features we don't use would burn 2–3 weeks for zero customer value. Tens of thousands of lines of pymongo would need rewrites. The document model (closer_brief, business_brief, nested memory entries, variable enrichment payloads) is genuinely better suited to Mongo than Postgres JSONB.

### When Supabase would actually make sense

- If the **portal becomes multi-user per client** with social login + row-level security
- If we ship a **mobile companion app** that needs realtime channels

Until then: keep Mongo for the agent OS. Add Supabase later only if/when one of those triggers fires.

---

## TL;DR

| Question | Answer |
|---|---|
| Insecure? | No — industry-standard unguessable-URL auth + HTTPS + HITL gate + scope locking |
| Will it scale? | Yes — Anthropic spend caps us long before infra does |
| Switch to Supabase? | Not now. Re-evaluate at multi-user portal or mobile-companion trigger |
| Biggest real risk | Onboarding throughput — solved by the waitlist gate |
