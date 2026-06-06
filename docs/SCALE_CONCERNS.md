# Scale-Stage Concerns & Tech Debt

Honest record of what's deferred and why — the things that are **fine for the
current stage** (solo founder, pre-/early-first-client) but will need attention
as load and the team grow. Plus findings from a whole-repo sweep.

Last updated: 2026-06-06 · Repo: ~260 source files, ~50k LOC, 35 test files.

---

## Whole-repo hygiene sweep — result

**PASS on the obvious risks:**
- No `eval(` / `exec(` / `shell=True` — no code-injection surface.
- No `verify=False` — no TLS bypass.
- No bare `except:` — errors are typed, not blanket-swallowed.
- No hardcoded API keys / secrets — all via `config.get_settings()` / env.

**Caveat:** only ~30 files (this session's adapters + inventions) were *deeply*
reviewed. The pre-existing ~230 files (original SDR funnel, EstateOS rent/KYC,
the 7 hidden suites, the 11.7k-line dashboard, `agent/brain.py`) were swept for
risk patterns but not line-by-line audited.

---

## Findings (prioritised)

| # | Severity | Area | Issue | Fix | When |
|---|---|---|---|---|---|
| 1 | **High (rule)** | Logging | **PII in `structlog`** — phones/emails passed as log fields in ~8 files (`webhooks.py`, `outreach.py`, `morning_brief_client.py`, `receipt_match.py`, `whatsapp_health.py`, `marketing.py`). Violates the "never log PII" rule. | One central structlog **redaction processor** that scrubs phone/email patterns from every event — one place, covers the whole repo. | **Soon** (compliance) |
| 2 | Medium | DB / async | **Sync `pymongo` inside `async` handlers** — project-wide (`get_db()` called in dozens of async routes + every inbound hook). Under real concurrency it blocks the event loop. | Migrate to **Motor** (async Mongo driver), or run blocking DB in a thread pool. Meaningful migration. | When concurrency bites (post first clients) |
| 3 | Medium | Testing | **Coverage is partial + mock-heavy.** 35 test files / 260 source. New adapters are unit-tested with faked deps; pre-existing suites + the dashboard are lightly tested; **no integration tests** against live Unipile/Meta/Anthropic/Mongo (CI runs with none). | Keep adding **contract tests** (started, `test_contracts.py`); add a **staging integration job** with real creds for the highest-risk paths. | Ongoing |
| 4 | Medium | Multi-instance | **APScheduler is in-process** (single `AsyncIOScheduler`). If Railway scales to >1 instance, cron jobs **double-fire** (rent chase, briefs, IMAP poll). | A distributed lock / leader election, or pin the scheduler to one worker. | Before horizontal scaling |
| 5 | Low | Channels | **Provider webhook payloads assumed** (Unipile email, Meta IG) — parsed from docs/knowledge, not a captured real payload. Shape-logging now added on parse-miss. | Validate against the **first real event** each, then tighten parsers. | At pilot |
| 6 | Low | Email/IMAP | The IMAP poller runs **all clients in one executor thread** every 3 min. | Thread pool / per-client task queue. | At ~dozens of email clients |
| 7 | Low | Webhooks | **No rate limiting / backpressure** on inbound webhooks; each message does several sync DB hooks (memory, outcomes, demand, haggle, identity) inline. | Queue inbound (e.g. a task runner) + cap per-message work. | At message-volume scale |
| 8 | Low | Data | **No DB-level schema validation** — relies on Pydantic at API boundaries; some collections written ad hoc. Indexes are ensured at lifespan (good). | Mongo schema validators on the money collections. | As the team grows |

---

## What is genuinely solid (don't re-litigate)

- **HITL choke point** — every outbound routes through `tools/hitl.queue_draft()`.
- **Pure cores + thin adapters** — the 5 inventions, escalation bands, negotiation,
  extraction are deterministic + well unit-tested.
- **Fail-safe gating** — flags off by default, fail to "off"; Meta channel dormant;
  encryption refuses plaintext.
- **Secrets** — Fernet at-rest for email/Meta tokens; HMAC webhook verification.
- **CI gate** — full suite on every push; red can't deploy.
- **Multi-tenant scoping** — `/estate/*` + memory scoped by client; isolation probes exist.

---

## The one to do soon

**#1 (PII in logs)** is the only finding that's a *rule violation* rather than a
scale trade-off. It's cheap to fix centrally (a structlog processor) and worth
doing before onboarding real customer traffic. Everything else is appropriately
deferred to "when scale actually demands it."
