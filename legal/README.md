# ReachNG — Legal Pack (Lawyer Review)

Four documents drafted ready for lawyer review. Every clause needing legal verification is marked **[LAWYER REVIEW]** so the lawyer can spot what to focus on.

| File | Purpose | Signed by |
|---|---|---|
| [`MSA.md`](MSA.md) | Master Service Agreement — the umbrella contract | Every client |
| [`DPA.md`](DPA.md) | Data Processing Agreement — NDPR-compliant | Every client |
| [`MUTUAL_NDA.md`](MUTUAL_NDA.md) | Two-way confidentiality | Every client |
| [`CLOSER_ADDENDUM.md`](CLOSER_ADDENDUM.md) | Lead ownership + HITL responsibility | Real-estate Closer clients only |

## Briefing notes for the lawyer

1. **NDPR registration** — can your firm file with NITDA, or should we DIY? Filing fee is ~₦20K.
2. **DPO appointment** — required only when we cross 10K records processed; please confirm the threshold and language.
3. **Liability cap** — drafted as 12 months of fees paid. Is that market for Lagos SaaS?
4. **Lagos Tenancy Law alignment** — Closer Addendum mentions quit-notice language for rent chase. Please confirm the 7-day final ultimatum wording is current.
5. **Forum** — drafted as Lagos High Court. Switch to arbitration (LCA / LMDC) if you prefer.
6. **AI-specific carve-outs** — we draft messages with Claude (Anthropic), every outbound is human-approved before send. The DPA should reflect that processing.

## What we are / aren't (one-pager for the lawyer)

- **What we are**: Nigerian SaaS platform that orchestrates AI-drafted, human-approved outbound messaging (WhatsApp + email) for SMEs across real estate and HR.
- **What we are not**: not a lender, not a payments provider, not a custodian of client funds, not a CRM. We process PII on behalf of our clients (data processor, not controller).
- **Sub-processors**: Anthropic (AI drafting), Unipile (WhatsApp gateway), MongoDB Atlas (storage), Railway (hosting).
- **PII categories**: full name, phone, email, address.
- **Geography**: Nigeria-first; data may transit AWS regions (Cape Town / Frankfurt) via sub-processors.

## How to use these drafts

1. Lawyer reviews and inserts changes against `[LAWYER REVIEW]` markers.
2. We accept the redlines and produce a final.
3. PDFs generated via Pandoc or any markdown-to-PDF converter for signature.
4. Counter-signed copies stored in Mongo against the `clients` document (`legal_pack` field) for audit.
