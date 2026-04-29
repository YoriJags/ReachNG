# Ideas Pipeline

[[Home]] | [[Build Log]] | [[Verticals]]

> Formula: **Painful manual workflow + publicly available data + AI layer + geography with zero competition**

---

## Idea 0 — PLUGng ⭐ HIGHEST PRIORITY

**What:** ReachNG for musicians. Scans artist presence → finds music blogs, playlist curators, A&Rs, radio producers, event promoters, brand managers → generates personalised pitches → sends at scale.

**Pain:** Artists spend months manually DMing blogs. No system exists for Lagos/African artists to get heard internationally.

**Warm lead:** David Avante (Mercury VI / PLUGng) → Bizzle Osikoya network. First client.

**Pricing:**
- Artist plan: ₦30,000/mo
- Manager plan: ₦80,000/mo (up to 5 artists)
- Label plan: ₦200,000/mo (unlimited roster)

**Build effort:** Low — reuses 80% of ReachNG. Add `artist` vertical + curators/blogs discovery layer.

**MVP path:**
1. Pitch David first — validate before building
2. Add `artist` vertical to discovery
3. Seed list of curators/blogs as starting dataset
4. Artist-specific Claude prompt templates
5. Track: playlist adds, bookings, blog features

**Why now:** Afrobeats/Amapiano exploding globally. Every artist needs international plugs. No competitor for Nigerian artists.

---

## Idea 1 — AI Voice Agent for Nigerian Businesses

**What:** AI answers calls for Lagos businesses — clinics, restaurants, salons. Speaks Nigerian English + Pidgin. Books appointments, qualifies leads, takes orders.

**Pain:** Every Lagos business misses calls. No Nigerian-specific AI voice product exists.

**Stack:** ElevenLabs or PlayHT for voice, Twilio for telephony, Claude for conversation logic.

---

## Idea 2 — WhatsApp Commerce Assistant

**What:** Business uploads product CSV → customers ask questions via WhatsApp → bot answers 24/7 with prices, availability, order taking.

**Pain:** SMEs in Lagos can't afford a customer service team but get flooded with WhatsApp inquiries.

**Build dependency:** Needs [[Integrations#Unipile]] inbound webhook first.

**Code reuse:** B2C CSV upload already built (`tools/csv_import.py`). Missing piece: inbound message handler + product lookup + Claude response loop.

---

## Idea 3 — POS Reconciliation Agent

**What:** Parses bank alerts (SMS/email) → matches transactions to POS records → flags discrepancies automatically.

**Pain:** Lagos business owners spend hours every week reconciling POS vs bank. High fraud risk.

**Build dependency:** Needs inbound message handler (SMS or email webhook).

---

## Idea 4 — Recruitment AI for Lagos Agencies

**What:** Job description in → candidate profiles scraped from LinkedIn/Apollo → personalised outreach to passive candidates → tracks responses.

**Pain:** Lagos recruitment agencies still do everything manually. No affordable ATS with Nigerian market context.

**Code reuse:** `recruitment` vertical already in ReachNG. Extend with CV parsing + JD matching.

---

## Idea 5 — Legal Document Automation

**What:** SMEs describe their need (lease agreement, service contract, NDA) → Claude generates Lagos-law-compliant document → lawyer reviews → delivered in 24h.

**Pain:** Basic legal docs cost ₦50–200k from Lagos lawyers. Most SMEs just skip them.

---

## Prioritisation

| Idea | Revenue Speed | Build Effort | Warm Lead | Priority |
|------|--------------|--------------|-----------|----------|
| PLUGng | Fast | Low (80% reuse) | Yes — David | 1st |
| Commerce Assistant | Fast | Medium | No | 2nd |
| Voice Agent | Medium | High | No | 3rd |
| POS Reconciliation | Fast | Medium | No | 4th |
| Recruitment AI | Medium | Low | No | 5th |
| Legal Docs | Medium | Medium | No | 6th |
