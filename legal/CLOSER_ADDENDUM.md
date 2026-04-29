# ReachNG Closer Addendum

This addendum supplements the [Master Service Agreement](MSA.md) and the [Data Processing Agreement](DPA.md) where the Client has subscribed to the **ReachNG Closer** suite (real-estate inbound lead handling).

---

## 1. Scope of Closer

The Closer suite:

- Captures inbound real-estate enquiries via WhatsApp, web form, and email forwarder.
- AI-classifies each new message and drafts the next outbound reply.
- Queues every draft in the Client's HITL inbox for explicit approval.
- Tracks lead stage progression (new → qualifying → ready → booked / lost / stalled).
- Hands over qualified leads to the Client with budget + timeline + objections summarised.

## 2. Lead ownership

- Each lead generated through Closer is the **exclusive property of the Client**.
- ReachNG does not share, resell, or use lead data for any other Client.
- ReachNG does not contact a Client's leads on behalf of any third party.
- Aggregated, de-identified statistics across the platform may be used by ReachNG for product improvement (in line with MSA §6).

## 3. Client's Closer-specific obligations

The Client shall:

1. Maintain a current and accurate **Closer Brief** (or BusinessBrief covering Closer fields) — product list, ICP, qualifying questions, red flags, never-say list, closing action.
2. Approve, edit, or skip every draft in the HITL queue. **Drafts auto-expire after 72 hours** if no action is taken.
3. Comply with **Lagos Tenancy Law** when issuing chase / quit notices through the Platform.
4. Honour every opt-out within 24 hours of receipt.
5. Not use the Closer suite to broker properties for which it does not have a documented mandate from the principal.

[LAWYER REVIEW] — confirm Lagos Tenancy Law alignment of any chase / quit-notice wording produced by the platform.

## 4. AI drafting and HITL responsibility

- Every outbound message is drafted by Claude (Anthropic) using the Client's BusinessBrief context.
- **No outbound message is sent without explicit Client approval** in the HITL queue.
- The Client bears final responsibility for the content of any approved message that is sent from its WhatsApp number, irrespective of whether the original draft was AI-generated.
- ReachNG warrants the technical fidelity of the drafting and queueing pipeline; ReachNG does NOT warrant the substantive accuracy of any specific AI-drafted message and the Client must read each draft before approving.

## 5. Compliance with WhatsApp policies

The Client acknowledges that:

- The platform sends messages from the Client's own WhatsApp number paired through Unipile.
- Meta enforces opt-out, throttling, and content rules; suspension of the Client's number is a Meta decision and outside ReachNG's control.
- ReachNG enforces protective rate-limits and warm-up caps to reduce suspension risk; the Client may not bypass these.

## 6. Sender warm-up

For new accounts, ReachNG enforces a **7-day warm-up window** during which daily send caps are reduced (typically: days 0-2 = 50/day, days 3-6 = 100/day, day 7+ = configured cap). The Client may not request the warm-up be lifted before day 7.

## 7. Pricing (real estate)

As set out in the Order Form. Default Closer pricing structure (where the Order Form is silent):

- One-time setup fee
- Monthly retainer
- Per-qualified-viewing fee, OR commission on closed deals (luxury tier)

[LAWYER REVIEW] — confirm whether commission-based pricing requires any additional licensing under Lagos real-estate / agency rules.

## 8. Termination consequences

On termination of the MSA:

- The Client retains full ownership of all leads in its Closer pipeline.
- ReachNG provides a one-time CSV export of all leads, threads, and stage history at no charge.
- ReachNG hard-deletes Closer data within 30 days of export confirmation, save where retention is required by law.

## 9. Order of precedence

Where any conflict arises between this Addendum and the MSA, this Addendum prevails on Closer-specific matters.

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
