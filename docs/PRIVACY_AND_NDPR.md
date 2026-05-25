# ReachNG — Privacy posture & NDPR alignment

**Audience:** prospects in regulated verticals (legal, clinics, fintech, advisory) who need to know exactly what happens to their customer data before signing. Hand this to a prospect's compliance officer; nothing in it is marketing.

**Last reviewed:** 2026-05-25.
**Owner:** Yori Ajagun (`yoriajagun08@gmail.com`).
**Jurisdiction:** Nigeria. Governed by the Nigeria Data Protection Act 2023 (NDPA) and the Nigeria Data Protection Regulation 2019 (NDPR).

---

## Plain-English summary

1. We never touch a customer payment. Money flows direct from your customer's bank to **your** Paystack subaccount or **your** business account. ReachNG holds zero funds.
2. Every message we draft for you waits for your tap. We do not auto-send anything by default. Architecturally enforced in `tools/hitl.py` — no code path bypasses your approval.
3. Each client business is fully isolated in our database. We test this nightly with an automated probe (`tests/test_isolation.py` + scheduler job at 03:00 Lagos) that writes a unique marker into Client A's scope and asserts Client B's reads cannot see it.
4. We log message metadata (timestamps, queue state, classifier verdicts) but **never PII** (no phone numbers, no names, no message bodies) in our server logs. Enforced by the project's structlog convention — see [`CLAUDE.md`](../CLAUDE.md#code-standards).
5. You can export all your data and request hard-deletion at any time. 30-day purge job runs after revocation.
6. We process all data inside **MongoDB Atlas (AWS af-south-1 — Cape Town)** with TLS in flight and AES-256 encryption at rest.

---

## Roles under NDPA / NDPR

| Role | Who | Scope |
|---|---|---|
| **Data Controller** | You (the SME / firm) | Your customers' personal data. You decide what's collected, why, and for how long. |
| **Data Processor** | ReachNG | We process data **only on your instructions**, never for our own purposes. We do not sell, share, or use your data to train any model outside your scope. |
| **Sub-processors** | Anthropic (Claude API), Unipile (WhatsApp routing), MongoDB Atlas (hosting), Railway (compute), Paystack (payments), OpenAI (Whisper voice transcription only) | Full list below with their roles, data they see, and their own DPAs. |

---

## What data we process for you

| Category | Purpose | Retention |
|---|---|---|
| **Customer contact details** (phone, name, sometimes email) | Identify who sent which message; route the draft back | Until you revoke or 90 days after client off-boards |
| **WhatsApp message content** (inbound + your approved outbound) | Draft personalised replies; reference past conversation | Same as above |
| **Voice-note audio** (inbound) | Transcribe via OpenAI Whisper; the transcript is treated like a text message; the raw audio is deleted within 24h | 24h max |
| **Payment-receipt images** (inbound) | OCR via Claude Vision; the extracted text is stored; the raw image is deleted within 24h | 24h max |
| **Customer memory entries** (durable facts you've learned about a customer) | Reference in future replies | Until you revoke |
| **Operational metadata** (timestamps, classifier intents, draft latency, approval state) | Show you the morning brief; measure EYO's quality; bill metering | 13 months |

We do **not** collect: government IDs, BVN, NIN, bank account credentials, card numbers, biometrics, geolocation, browser fingerprints, third-party cookies.

---

## Data-flow at a glance

```
 Customer's WhatsApp
       │
       ▼
 Unipile (or Meta Cloud API) — TLS, authenticated webhook
       │
       ▼
 ReachNG webhook handler (api/webhooks.py)
       │
       ├── Whisper transcribe (voice only) — audio deleted in 24h
       ├── Claude Vision OCR (receipt only) — image deleted in 24h
       └── Persist to MongoDB Atlas (af-south-1) — TLS + at-rest encryption
              │
              ▼
       Claude Haiku draft (server-side, scoped to your client_id)
              │
              ▼
       HITL queue — waits for YOUR tap
              │
              ▼ (only after your approval)
       Unipile send — message flows from YOUR WhatsApp number to the customer
```

---

## Sub-processor register

| Sub-processor | Role | Data seen | Where | DPA |
|---|---|---|---|---|
| **Anthropic** (Claude API) | LLM drafting + classification | Message bodies + system prompt | US, EU regions | https://www.anthropic.com/legal/dpa |
| **Unipile** | WhatsApp / messaging API gateway | Inbound + outbound messages, sender phone numbers | EU | https://www.unipile.com/legal |
| **MongoDB Atlas** | Primary database | All persisted data | AWS af-south-1 (Cape Town) | https://www.mongodb.com/legal/dpa |
| **Railway** | Compute / hosting | In-flight data only (not persisted on Railway disks) | US-west | https://railway.com/legal/dpa |
| **Paystack** | Payments + subaccount routing | Payment metadata only, never message content | Nigeria | https://paystack.com/terms |
| **OpenAI** (Whisper) | Voice-note transcription | Audio buffer (deleted by OpenAI per their retention) | US | https://openai.com/policies/data-processing-addendum |
| **PostHog** | Product analytics | Anonymised event metadata, never message content | EU (self-hosted option available) | https://posthog.com/dpa |

Adding a sub-processor requires 30-day prior notice to you. You can object; if you do, we work out an alternative or you off-board with prorated refund.

---

## Security controls

| Control | Where it lives | How to verify |
|---|---|---|
| TLS 1.2+ for every external hop | All HTTPS endpoints + Unipile/Anthropic/Mongo connection strings | `curl -vI` any URL; check Railway TLS cert |
| AES-256 at rest on MongoDB | Atlas default | Atlas console → Security |
| Per-client data isolation | `services/client_memory.py`, `services/scorecard.py`, `services/outcome_learning.py` — every read/write filtered by `client_id` | `tests/test_isolation.py` + 03:00 Lagos scheduler job writes to `isolation_audits` collection |
| No PII in server logs | structlog convention enforced in code review + `CLAUDE.md` rule | Grep our `*.log` files for any phone/name — should return zero |
| HITL gate on every outbound | `tools/hitl.py::queue_draft()` — only send path | Read the file. There is no other send code path. |
| Tone scrub | `tools/tone.py::scrub_endearments()` | Strips "babe", "love", "dear" etc from every draft before queueing |
| Webhook authentication | HMAC-SHA256 signature verification for Meta, shared `Unipile-Auth` header for Unipile in `api/webhooks.py` | Reject any inbound without valid provider authentication in production |
| Portal token entropy | `secrets.token_urlsafe(24)` — 192 bits | ~10⁵⁷ possible tokens, unguessable |

---

## Data subject rights (your customers' rights)

Under NDPA s.34–37, your customers can request:

| Right | Our SLA |
|---|---|
| **Access** — copy of their data | 14 days from your request to us |
| **Rectification** — correct an error | Same business day on request |
| **Erasure** — hard-delete | Within 30 days; tombstoned immediately, purged on next nightly cleanup |
| **Portability** — machine-readable export | CSV/JSON export from your portal at any time |
| **Object / restrict** — stop processing | Immediate; turn off the relevant feature in your portal |

You handle the customer-facing relationship; we provide the data + the export tools. Self-serve export buttons in your portal: `/portal/{token}/data-export`, `/portal/{token}/data-delete`.

---

## Incident response

| Incident type | Notification SLA to you | Regulator notification |
|---|---|---|
| Confirmed data breach affecting your data | 24 hours | NDPC within 72 hours (NDPA s.40), as Processor we notify you immediately |
| Suspected breach (under investigation) | 72 hours | N/A unless confirmed |
| Sub-processor breach | 48 hours from their notice to us | We notify you; you decide whether to onward-notify your customers |

Audit log of every data access event is retained for 13 months.

---

## Off-boarding

When you terminate:

1. Outbound queue stops immediately.
2. Within 30 days: your full export is delivered (Mongo collections scoped to your `client_id`, CSV or JSON).
3. Within 60 days: all your data is purged from primary + backups.
4. Audit log of the deletion is signed and kept for 13 months.

---

## What we do NOT do

- We do not train any model (ours or a sub-processor's) on your data.
- We do not sell, lease, or share your data with any third party except the sub-processors listed above.
- We never use your data for marketing.
- We do not place advertising cookies or behavioural tracking on your portal.
- We do not send any message from your WhatsApp number without your explicit tap.

---

## How to use this document

- **Internal sales:** attach as PDF to enterprise / regulated-vertical prospect proposals.
- **Compliance officers:** treat as our committed DPA terms. Counter-signing the MSA + this doc constitutes acceptance.
- **Engineering:** any change to data flow, retention, or sub-processors must update this doc in the same PR.

For questions or to request a counter-signed DPA: **yoriajagun08@gmail.com**.
