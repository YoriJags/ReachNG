# Master Service Agreement (MSA)

**Between**: ReachNG (Service Provider) — operating address: Lagos, Nigeria.
**And**: [CLIENT LEGAL NAME], CAC RC [NUMBER] (Client) — operating address: [CLIENT ADDRESS].
**Effective Date**: [DATE].

---

## 1. Services

ReachNG provides a software-as-a-service platform that:

- Discovers leads (Closer suite) or accepts uploaded contact lists (BYO Leads).
- Drafts personalised outbound messages using AI, scoped to the Client's Business Brief.
- Holds every draft in a Human-in-the-Loop (HITL) queue for explicit Client approval.
- Sends approved messages via the Client's own WhatsApp number (paired through Unipile).
- Routes inbound replies, classifies intent, drafts next-step responses, and surfaces qualified leads to the Client.
- Provides per-tenant analytics, audit trails, and rent / invoice / debt chase workflows where applicable.

ReachNG does NOT: hold Client funds, provide legal or financial advice, lend money, or act as a payment institution.

## 2. Term and termination

- Initial term: **12 months** from the Effective Date.
- Auto-renews for further 12-month periods unless either party gives **30 days' written notice** before renewal.
- Either party may terminate immediately for material breach uncured for 14 days after written notice.
- On termination, Client data is exported on request and **hard-deleted within 30 days** unless retention is required by law.

[LAWYER REVIEW] — confirm the term length, renewal mechanism, and termination triggers are market for Lagos SaaS.

## 3. Fees and payment

- Fees as set out in the **Order Form** signed by both parties (which forms part of this MSA).
- Invoiced **monthly in advance**. Payable within **14 days** of invoice date.
- Overdue amounts attract interest at the lesser of **1.5% per month** or the maximum rate permitted by Nigerian law.
- All fees exclusive of VAT and any applicable Nigerian taxes; Client pays gross of withholding tax where required.

[LAWYER REVIEW] — confirm interest rate is permitted under Nigerian law; confirm WHT treatment.

## 4. Client obligations

The Client shall:

- Maintain a complete and accurate Business Brief (the AI uses this as its source of truth).
- Hold a lawful basis under NDPR for every contact uploaded or otherwise processed on the Platform; attest to that basis at upload.
- Approve or skip every draft in the HITL queue; not bypass the queue.
- Use the Platform only for outreach to its own contacts, not on behalf of unrelated third parties.
- Provide ReachNG with operational notices (escalations, opt-out requests, data subject access requests) within reasonable time.

## 5. ReachNG obligations

ReachNG shall:

- Keep the Platform commercially available 24×7, with **planned maintenance windows** announced where practicable.
- Process Client personal data only on Client instructions, in line with the [Data Processing Agreement](DPA.md).
- Maintain encryption at rest and in transit, role-based access controls, and audit logs.
- Notify the Client of a confirmed personal data breach within **72 hours**.
- Not use Client data to train models or sell to third parties.

## 6. Intellectual property

- The **Platform**, including all source code, prompts, AI orchestration logic, and the BusinessBrief framework, is and remains the property of ReachNG.
- **Client Data** (contact lists, leads, inbound replies, brief content) is and remains the property of the Client.
- Client grants ReachNG a non-exclusive licence to process Client Data solely for the purpose of providing the Services.
- ReachNG may use **aggregated, de-identified statistics** (e.g. "average reply rate across cooperatives") for product improvement, but never Client-identifiable data.

## 7. Liability

- Each party's aggregate liability under or in connection with this MSA is **capped at the fees paid by the Client to ReachNG in the 12 months preceding the event giving rise to the claim**.
- Neither party is liable for **indirect, consequential, or special damages**, loss of profits, or loss of business opportunity.
- The cap and exclusions do NOT apply to: (a) payment of fees due, (b) breach of confidentiality, (c) wilful misconduct, (d) fraud, or (e) breach of data protection obligations leading to regulatory fine.

[LAWYER REVIEW] — confirm 12-month cap is market and the carve-outs are appropriate.

## 8. Confidentiality

Each party shall hold the other's confidential information in confidence and not disclose or use it other than for the performance of this MSA. The detailed terms are set out in the [Mutual NDA](MUTUAL_NDA.md), which forms part of this Agreement.

## 9. Data protection

The parties' respective rights and obligations under the Nigeria Data Protection Act 2023 and the NDPR are set out in the [Data Processing Agreement](DPA.md), which forms part of this Agreement.

## 10. Force majeure

Neither party is liable for delay or failure caused by events beyond reasonable control, including network outages, third-party platform suspensions (Unipile, Anthropic, Meta WhatsApp), regulatory changes, civil unrest, or natural disaster — provided the affected party gives prompt notice and uses reasonable efforts to mitigate.

## 11. Suspension

ReachNG may suspend the Services on notice if:

- The Client's WhatsApp account is suspended by Meta or has an opt-out rate above 3% in 24 hours.
- The Client's Business Brief is incomplete (gating prospecting outreach).
- The Client is materially overdue on fees (more than 30 days).
- The Client uses the Platform unlawfully or in breach of NDPR.

Suspension does not relieve the Client of fees due for the suspension period.

## 12. Subcontractors and sub-processors

ReachNG uses the following sub-processors as of the Effective Date:

| Sub-processor | Purpose | Region |
|---|---|---|
| Anthropic | AI message drafting | USA |
| Unipile | WhatsApp gateway | EU |
| MongoDB Atlas | Data storage | AWS Cape Town / Frankfurt |
| Railway | Application hosting | USA |

ReachNG will give the Client **30 days' notice** of any new sub-processor; Client may object in writing.

[LAWYER REVIEW] — confirm sub-processor list + notice period; check whether NDPR cross-border requirements demand additional safeguards.

## 13. Governing law and disputes

- Governed by the laws of the **Federal Republic of Nigeria**.
- Disputes referred first to good-faith negotiation between named representatives for **30 days**.
- Failing resolution, disputes submitted to the exclusive jurisdiction of the **Lagos State High Court**.

[LAWYER REVIEW] — confirm forum (Lagos High Court vs LCA / LMDC arbitration) and governing law.

## 14. Notices

- All notices in writing, sent to the email addresses on the Order Form.
- Notice deemed received on the next business day after sending.

## 15. Entire agreement

This MSA, together with the Order Form, the [DPA](DPA.md), the [Mutual NDA](MUTUAL_NDA.md), and the [Closer Addendum](CLOSER_ADDENDUM.md) (where applicable), constitutes the entire agreement between the parties.

---

## Signature block

**ReachNG**

Signed: ______________________
Name: [REACHNG SIGNATORY]
Title: [TITLE]
Date: ______________________

**Client**

Signed: ______________________
Name: [CLIENT SIGNATORY]
Title: [TITLE]
Date: ______________________
