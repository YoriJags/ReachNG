# Data Processing Agreement (DPA)

This DPA forms part of the [Master Service Agreement](MSA.md) between ReachNG (Processor) and [CLIENT LEGAL NAME] (Controller). It governs ReachNG's processing of personal data on behalf of the Client under the **Nigeria Data Protection Act 2023 (NDPA)**, the **NDPR 2019**, and any implementing regulations.

---

## 1. Definitions

Terms used in this DPA have the meanings set out in the NDPA / NDPR. In particular: **Data Subject**, **Personal Data**, **Processing**, **Data Controller**, **Data Processor**, and **Sub-processor**.

## 2. Roles

- The **Client** is the **Data Controller** of all Personal Data uploaded to or generated through the Platform regarding the Client's contacts, leads, employees, and tenants.
- **ReachNG** is the **Data Processor** acting on documented instructions from the Client.
- Where ReachNG independently determines purposes for its own business operations (billing, security monitoring, aggregated analytics), it acts as a **Data Controller** for those limited purposes.

## 3. Categories of Personal Data processed

| Category | Source | Purpose |
|---|---|---|
| Full name | Client upload, Closer intake | Outreach personalisation |
| Phone number | Client upload, Closer intake | WhatsApp delivery |
| Email | Client upload, Closer intake | Email delivery |
| Address / area | Client upload, Closer intake | Lead context |
| Inbound message content | Closer / reply router | Reply classification + drafting |
| Engagement metadata | Platform-generated | Status tracking, opt-out enforcement |

## 4. Processing instructions

ReachNG processes Personal Data only:

- To deliver the Services described in the MSA.
- On the Client's documented instructions (including instructions transmitted through the Platform itself, e.g. uploading a list, approving a draft).
- As required by Nigerian law, with prior notice to the Client where lawful.

ReachNG shall promptly notify the Client if, in its opinion, an instruction infringes the NDPA / NDPR.

## 5. Lawful basis (Controller's responsibility)

The **Client** warrants that for every Data Subject whose data it loads to the Platform, it holds a **lawful basis** under NDPR — typically: (a) existing customer relationship, (b) explicit opt-in, or (c) legitimate interest with a documented assessment.

The Client attests to this lawful basis at the point of upload (consent attestation gate).

## 6. ReachNG's obligations

ReachNG shall:

1. **Confidentiality** — ensure that personnel authorised to process Personal Data are bound by confidentiality.
2. **Security** — implement appropriate technical and organisational measures, including:
   - encryption in transit (TLS 1.2+) and at rest (AES-256 or equivalent),
   - role-based access controls and least-privilege principles,
   - audit logs of all access to Personal Data,
   - environment isolation between Clients (multi-tenant scoping is a P0 invariant).
3. **Sub-processors** — engage sub-processors only under a written contract that imposes equivalent obligations to those in this DPA.
4. **Sub-processor list** — maintain the current list (see MSA §12) and give **30 days' notice** of changes.
5. **Data Subject requests** — assist the Client in responding to Data Subject access, rectification, erasure, and portability requests within the timelines required by NDPR.
6. **Breach notification** — notify the Client of any confirmed personal data breach **within 72 hours** of discovery, with information sufficient to enable the Client to fulfil its own NDPC notification duty.
7. **Data Protection Impact Assessment (DPIA)** — provide reasonable assistance to the Client where the Client must conduct a DPIA.
8. **Audit rights** — once per 12-month period, on 30 days' written notice, allow the Client (or its independent auditor under NDA) to verify ReachNG's compliance with this DPA.
9. **Return / deletion** — on termination or on Client request, return or hard-delete all Personal Data (and copies) within 30 days, save where retention is required by Nigerian law.

[LAWYER REVIEW] — confirm 72-hour breach window and 30-day deletion are aligned with current NDPC guidance.

## 7. Cross-border transfers

Where Personal Data leaves Nigeria via sub-processors (AWS Cape Town, AWS Frankfurt, Anthropic in the US, Unipile in the EU), ReachNG ensures an adequate level of protection by:

- choosing sub-processors with recognised data-protection frameworks,
- relying on the contractual safeguards built into each sub-processor's standard terms,
- documenting the lawful transfer basis under the NDPR cross-border transfer rules.

[LAWYER REVIEW] — confirm whether NDPC currently requires SCCs or other instruments; update if so.

## 8. Suppression and opt-outs

Any inbound reply classified as `opted_out` (typical triggers: STOP, UNSUBSCRIBE, REMOVE, "stop messaging me") is **immediately and permanently** added to a per-Client suppression list. The Data Subject is **never re-messaged** on any campaign on the Platform.

If a Data Subject contacts the Client directly to opt out, the Client must mark them opted-out in the portal.

## 9. Records of Processing

ReachNG maintains records of processing activities in line with the NDPR Article 5(1)(c) requirements. The Client may request a copy on reasonable notice.

## 10. Data Protection Officer (DPO)

- The **Client** confirms whether it has appointed a DPO and provides DPO contact details.
- **ReachNG** has appointed [REACHNG DPO NAME, EMAIL] as its DPO.

[LAWYER REVIEW] — advise whether ReachNG must formally appoint a DPO at our current scale, or only above the 10K-records threshold.

## 11. Liability

The liability provisions in MSA §7 apply to claims arising under this DPA, **except** that no cap or exclusion limits a party's obligation to pay regulatory fines, penalties, or sanctions imposed by NDPC on the other party as a direct consequence of that party's breach of this DPA.

## 12. Order of precedence

Where any conflict arises between this DPA and the MSA, this DPA prevails on data-protection matters.

---

## Signature block

**ReachNG (Processor)**

Signed: ______________________
Name: [REACHNG SIGNATORY]
Title: [TITLE]
Date: ______________________

**Client (Controller)**

Signed: ______________________
Name: [CLIENT SIGNATORY]
Title: [TITLE]
Date: ______________________
