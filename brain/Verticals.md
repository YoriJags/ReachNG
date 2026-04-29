# Verticals

[[Home]] | [[Campaign Flow]] | [[Ideas Pipeline]]

---

## Active Verticals (7)

| Vertical | Discovery Queries | Apollo Titles | Status |
|----------|-------------------|---------------|--------|
| `real_estate` | property development, real estate agency, housing developer | CEO, MD, Head of Sales, Property Manager | Active |
| `recruitment` | staffing agency, HR consulting, executive search | HR Director, Head of Talent, Recruitment Manager | Active |
| `events` | event planning company, corporate event organiser | Events Director, Head of Events, CEO | Active |
| `fintech` | fintech startup, payment solution, digital banking | CEO, CTO, Head of Partnerships | Active |
| `legal` | law firm, legal services, corporate lawyer | Managing Partner, Senior Advocate, Head of Legal | Active |
| `logistics` | logistics company, freight forwarding, supply chain | CEO, Operations Director, Head of Logistics | Active |
| `agriculture` | agribusiness, farm produce, food processing, agro allied | CEO, Farm Manager, Head of Agribusiness | Active |

---

## Discovery Sources Per Vertical

### Google Maps (`tools/discovery.py`)
- 3–5 query variants per vertical
- `textsearch` API with `region=ng` and city filter
- Returns: name, phone, address, rating, place_id

### Apollo.io (`tools/apollo_discovery.py`)
- Keyword + title matching per vertical
- Free plan: org search only (no emails)
- Paid ($49/mo): people search with decision-maker emails

### Social (`tools/social.py`)
- TikTok hashtags via Apify
- Twitter/X via bearer token search
- Instagram signals (no scraping — ToS violation)

---

## Upcoming Vertical

### `artist` — PLUGng
See [[Ideas Pipeline]] → Idea 0

Target discovery sources:
- Music blogs (crawl Google: "Lagos music blog")
- Spotify playlist curators (Chartmetric API or manual seed list)
- Radio producers (Google Maps: "radio station Lagos")
- A&Rs at labels (Apollo: music industry titles)
- Event promoters (Apollo + Google Maps)
- Brand managers (Apollo: "brand partnerships" titles)
