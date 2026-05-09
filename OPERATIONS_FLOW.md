# ReachNG — Operations Flow

Two parallel pipelines, one shared brain. This document is the canonical mental model.

- **SDR pipeline** = ReachNG's own outreach. Yori → Lagos SMEs.
- **Client pipeline** = a paying client's outreach. Client's customer → ReachNG draft → Client.

Both share the same Haiku model and the same HITL approval gate.

---

## 1. The two pipelines side-by-side

```mermaid
flowchart LR
    subgraph SDR["🟠 SDR PIPELINE — Our own outreach to Lagos SMEs"]
        D1[Maps / Apollo / Apify Discovery]
        D2[Apify Enrich<br/>decision_maker, title]
        D3[Vertical Classify<br/>real_estate / hospitality / etc]
        D4[Haiku Draft<br/>vertical prompt + signals]
        D5[HITL Queue]
        D6{Yori<br/>approves?}
        D7[Send via Unipile<br/>email or WhatsApp]
        D8[Inbound Reply Webhook]
        D9[Reply Classifier<br/>interested / not / question]
        D10[Auto-draft next move]

        D1 --> D2 --> D3 --> D4 --> D5 --> D6
        D6 -->|approve| D7
        D6 -->|edit| D7
        D6 -->|skip| D5
        D7 --> D8 --> D9 --> D10 --> D5
    end

    subgraph CLIENT["🔵 CLIENT PIPELINE — Paying client's customers reach them"]
        C1[Client's customer<br/>WhatsApp inbound]
        C2[Webhook lookup by<br/>whatsapp_account_id]
        C3{Active<br/>client?}
        C4{Holding Reply<br/>set + Autopilot OFF<br/>+ no send in 24h?}
        C5[Send Holding Reply<br/>instantly]
        C6{closer_enabled?}
        C7[Closer Brain<br/>create lead + draft]
        C8{Autopilot ON<br/>and safe?}
        C9[Auto-send via Unipile]
        C10[HITL Queue]
        C11{Client<br/>approves?}
        C12[Send from client's<br/>WhatsApp number]

        C1 --> C2 --> C3
        C3 -->|yes| C4
        C3 -->|no| Z[Log + ignore]
        C4 -->|yes| C5
        C4 -->|no| C6
        C5 --> C6
        C6 -->|yes| C7 --> C8
        C8 -->|yes| C9
        C8 -->|no| C10 --> C11
        C11 -->|approve| C12
        C11 -->|edit| C12
    end

    SDR -.shares.-> BRAIN[(🧠 Same Haiku model<br/>Same HITL gate<br/>Different prompt stack)]
    CLIENT -.shares.-> BRAIN
```

---

## 2. The drafting prompt stack (how a single message gets composed)

This is the layered system prompt that wraps every Haiku call. Each layer adds context the layer above doesn't have.

```mermaid
flowchart TD
    A[1. system.txt<br/>— ReachNG product catalog<br/>— principles<br/>— message rules]
    B[2. _nigerian_context.txt 🆕<br/>— payment rails, regulators<br/>— seasonal triggers<br/>— honorifics, pain language]
    C[3. self_brief.txt or client_brief<br/>SDR mode → ReachNG voice<br/>Client mode → Business Brief]
    D[4. vertical_primer.txt<br/>real_estate / hospitality /<br/>education / legal / etc.]
    E[5. lead_context_signals<br/>— Maps rating, reviews<br/>— enrichment.decision_maker<br/>— IG handle, place categories]
    F[6. user_message<br/>actual prospect/customer text]
    G((Haiku 4.5))
    H[draft]

    A --> B --> C --> D --> E --> F --> G --> H

    style A fill:#1a1a1a,color:#fff
    style B fill:#0c4a6e,color:#fff
    style C fill:#1a1a1a,color:#fff
    style D fill:#1a1a1a,color:#fff
    style E fill:#1a1a1a,color:#fff
    style F fill:#7c2d12,color:#fff
    style G fill:#ff5500,color:#fff
    style H fill:#16a34a,color:#fff
```

🆕 = the layer being added next session (Nigerian Market Fluency).

---

## 3. Vertical routing (which prompt file fires)

Every lead has a `vertical` tag. The drafter loads `agent/prompts/{vertical}.txt`. If unknown, falls back to `general` (a future generic prompt).

```mermaid
flowchart LR
    Lead[New lead<br/>arrives] --> V{vertical<br/>tag?}
    V -->|real_estate| R[real_estate.txt<br/>146 lines ⭐]
    V -->|hospitality| HO[hospitality.txt 🆕]
    V -->|education| ED[education.txt 🆕]
    V -->|professional_services| PS[professional_services.txt 🆕]
    V -->|small_business| SB[small_business.txt<br/>71 lines → 120+]
    V -->|legal| L[legal.txt<br/>52 lines → 120+]
    V -->|fintech| F[fintech.txt<br/>51 lines → 120+]
    V -->|fitness| FI[fitness.txt<br/>47 lines → 120+]
    V -->|recruitment| RC[recruitment.txt<br/>61 lines → 120+]
    V -->|logistics| LO[logistics.txt<br/>70 lines → 120+]
    V -->|events| E[events.txt<br/>40 lines → 120+]
    V -->|auto| AU[auto.txt<br/>47 lines → 120+]
    V -->|insurance| I[insurance.txt<br/>47 lines → 120+]
    V -->|cooperatives| CO[cooperatives.txt<br/>47 lines → 120+]
    V -->|agriculture| AG[agriculture.txt<br/>40 lines → 120+]
    V -->|agency_sales| AS[agency_sales.txt<br/>86 lines → 120+]
    V -->|clinics| CL[clinics.txt 🆕]

    R --> Draft((Haiku draft))
    HO --> Draft
    ED --> Draft
    PS --> Draft
    SB --> Draft
    L --> Draft
    F --> Draft
    FI --> Draft
    RC --> Draft
    LO --> Draft
    E --> Draft
    AU --> Draft
    I --> Draft
    CO --> Draft
    AG --> Draft
    AS --> Draft
    CL --> Draft

    style R fill:#16a34a,color:#fff
    style HO fill:#dc2626,color:#fff
    style ED fill:#dc2626,color:#fff
    style PS fill:#dc2626,color:#fff
    style CL fill:#dc2626,color:#fff
```

⭐ = current gold standard. 🆕 = missing, to build. The rest are getting brought up to gold standard.

---

## 4. Inbound message routing — single picture

When a WhatsApp comes in, this is exactly what happens:

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant U as Unipile
    participant W as /webhooks/whatsapp
    participant DB as MongoDB
    participant H as Holding Reply
    participant CL as Closer Brain
    participant Q as HITL Queue
    actor Y as Client / Yori

    C->>U: WhatsApp message
    U->>W: POST inbound payload
    W->>DB: Find client by<br/>whatsapp_account_id
    alt no active client
        W->>DB: Log inbound, return
    else active client
        W->>DB: Check holding_message<br/>+ autopilot off<br/>+ no send in 24h
        opt all three true
            W->>H: Fire holding_message
            H->>U: Send instantly
            U->>C: "Thanks, we'll be back shortly"
            W->>DB: Log holding_replies_sent
        end
        opt closer_enabled
            W->>CL: create_lead + draft_next_move
            CL->>Q: queue_draft (HITL)
        end
        Q->>Y: Show in admin dashboard
        Y->>Q: approve / edit / skip
        Q->>U: Send approved draft
        U->>C: Real reply
    end
```

---

## 5. Operational state — what each toggle controls

```mermaid
stateDiagram-v2
    [*] --> Inactive: client created
    Inactive --> ManualHITL: payment_status = paid
    ManualHITL --> Autopilot: toggle ON
    Autopilot --> ManualHITL: toggle OFF
    ManualHITL --> SignalListening: toggle ON
    SignalListening --> ManualHITL: toggle OFF

    state ManualHITL {
        [*] --> Drafting
        Drafting --> Queued
        Queued --> Sent: client approves
        Queued --> Skipped: client skips
        Sent --> [*]
    }

    state Autopilot {
        [*] --> AutoDrafting
        AutoDrafting --> SafetyCheck
        SafetyCheck --> AutoSent: low risk
        SafetyCheck --> Queued: high risk → HITL
    }

    note right of Autopilot
        Holding reply DOES NOT fire
        when autopilot is on — AI replies fast
    end note
```

---

## 6. Where each piece of code lives

| Concern | File |
|---------|------|
| Discovery (Maps) | `tools/discovery.py` |
| Discovery (Apify) | `tools/apify_discovery.py` + `tools/apify_enrich.py` |
| SDR drafting brain | `agent/brain.py::generate_outreach_message()` |
| Vertical prompts | `agent/prompts/{vertical}.txt` |
| HITL queue | `tools/hitl.py::queue_draft()` |
| Inbound webhook | `api/webhooks.py` |
| Holding reply | `api/webhooks.py::_maybe_send_holding_reply()` |
| Closer brain | `services/closer/brain.py::draft_next_move()` |
| Universal sender | `tools/outreach.py::send_whatsapp_for_client()` |
| Demo portals | `services/demo_datasets.py` + `templates/portal_demo.html` |
| Admin dashboard | `templates/dashboard.html` |
| Client portal | `templates/portal.html` |
| Business Brief (next session) | `services/brief/` (to build) |

---

## 7. Reading order for new contributors

If you're new to the codebase, read these in order:

1. `CLAUDE.md` — project rules + stack
2. `PLAN.md` — what's being built right now
3. `BACKLOG.md` — what's queued
4. **This file** — how it all fits together
5. `agent/prompts/system.txt` + `self_brief.txt` — the voice
6. `agent/prompts/real_estate.txt` — the gold-standard vertical prompt example
7. `api/webhooks.py` — single source of truth for inbound routing
