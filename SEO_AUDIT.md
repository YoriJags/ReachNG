# ReachNG — SEO Audit

Date: 2026-05-09
Auditor: code review of live site + repo

---

## TL;DR

**ReachNG has no public-facing presence.** A prospect who Googles "ReachNG" or clicks any cold link lands on a 401 Basic Auth modal because `/` redirects to the password-gated `/dashboard`. Every other surface (demo portals, admin) is auth-gated or tucked away. There is **no SEO equity to speak of** — but the gap is fixable in 1–2 days of focused build.

**Verdict: do not run an SEO campaign yet. Build the marketing site first, then run it.**

---

## Current state — line by line

| Surface | Status |
|---------|--------|
| Public landing page (`/`) | ❌ Redirects to auth-gated dashboard |
| `/about`, `/how-it-works`, `/pricing` | ❌ Don't exist |
| `/blog` or any content | ❌ Doesn't exist |
| `/case-studies` | ❌ Doesn't exist |
| `robots.txt` | ❌ Missing |
| `sitemap.xml` | ❌ Missing |
| OpenGraph (`og:`) tags on portal_demo.html | ❌ Missing — sharing the demo URL gives no rich preview |
| Twitter Card tags | ❌ Missing |
| Schema.org JSON-LD (Organization, SoftwareApplication, FAQPage) | ❌ Missing |
| Canonical domain | ⚠️ Only `reachng-production.up.railway.app` — not `reachng.ng` or similar branded domain |
| HTTPS | ✅ Provided by Railway |
| Mobile responsive | ✅ Demo portal templates are responsive |
| Page speed | ✅ Demo portal is light (no framework, vanilla JS) |
| Existing inbound search traffic | 0 — nothing to index |

---

## Highest-impact fixes (ranked by ROI)

### 1. Build the marketing site (BLOCKING — 2 days)

Without this, nothing below matters.

**Pages required:**
- `/` — hero ("an agentic employee for Nigerian SMEs"), 60-second product demo embed, social proof slot (logos when available), CTA "see live demo" → `/portal/demo`
- `/how-it-works` — three-step explainer (your leads → agent drafts + you approve → done), screenshots of dashboard
- `/pricing` — concrete numbers per tier (₦80K / ₦150K / ₦300K), "what's included" matrix, annual = save 15% angle, FAQ section
- `/for-restaurants`, `/for-real-estate`, `/for-schools`, `/for-legal`, `/for-small-business` — vertical-specific landers, link to their demo portal, vertical-specific pain language
- `/about` — founder face (Yori), story, why Nigeria, why SMEs
- `/contact` — WhatsApp CTA + email + Calendly link

**Build approach:** keep it on the existing FastAPI + Jinja stack. Add `templates/marketing/` directory + `api/marketing.py` router. Reuse the demo portal CSS variables for visual consistency. Should take 2 focused days.

---

### 2. Set up `robots.txt` + `sitemap.xml` (~1 hour)

```
# robots.txt — at /robots.txt
User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /admin
Disallow: /api
Disallow: /webhooks
Disallow: /portal/  # token URLs are private
Allow: /portal/demo
Sitemap: https://reachng.ng/sitemap.xml
```

`sitemap.xml` lists every public marketing page + each `/portal/demo/{vertical}` (5 verticals). Auto-regenerate via FastAPI route. Trivial to ship.

---

### 3. Schema.org JSON-LD on every page (~2 hours)

On `/`:
```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "ReachNG",
  "url": "https://reachng.ng",
  "logo": "https://reachng.ng/static/logo.png",
  "description": "Agentic employee for Nigerian SMEs — drafts replies, qualifies leads, follows up, runs back-office.",
  "founder": { "@type": "Person", "name": "Oluyori Ajagun" },
  "areaServed": { "@type": "Country", "name": "Nigeria" },
  "sameAs": [
    "https://twitter.com/reachng_",
    "https://linkedin.com/company/reachng",
    "https://instagram.com/reachng"
  ]
}
```

Plus:
- `SoftwareApplication` markup on `/` and `/how-it-works`
- `FAQPage` on `/pricing` and `/how-it-works`
- `BreadcrumbList` on vertical pages

Lift: Google understands what you are without guessing. Faster ranking, eligibility for rich results.

---

### 4. OpenGraph + Twitter Cards (~30 mins per page)

Right now if you paste your demo URL into WhatsApp, IG DM, or Twitter, you get a naked link. Add this to every public template:

```html
<meta property="og:title" content="ReachNG — Mercury Lagos Demo">
<meta property="og:description" content="See how a Lagos rooftop venue handles 47 enquiries / week with zero leakage.">
<meta property="og:image" content="https://reachng.ng/static/og-mercury.png">
<meta property="og:url" content="https://reachng-production.up.railway.app/portal/demo">
<meta name="twitter:card" content="summary_large_image">
```

Generate one OG card image per vertical demo (₦1500 in Canva or 30 mins in Figma). Sharing demos in WhatsApp groups becomes visual.

---

### 5. Buy and route a real domain (BEFORE publishing)

`reachng-production.up.railway.app` doesn't sound like a real product. Options:
- `reachng.ng` — preferred, ₦15K/year on Whogohost
- `reachng.co` — good fallback if `.ng` taken
- `reach.ng` — short, premium
- `usereachng.com` — last resort

Configure CNAME on Railway → cert auto-provisions. **Do this BEFORE building the marketing site** so all internal URLs reference the final domain.

---

### 6. Target keywords (Nigerian-market specific)

Don't compete on generic global terms ("AI sales agent", "WhatsApp automation"). Target Lagos/Nigerian intent:

**Primary tier (transactional intent, Lagos-heavy):**
- "WhatsApp automation Nigeria"
- "AI receptionist Lagos"
- "WhatsApp business chatbot Lagos"
- "lead follow-up tool Nigeria"
- "AI for Lagos restaurants" / "AI for Lagos real estate agents"
- "missed bookings WhatsApp"

**Secondary tier (informational, easier to rank):**
- "how to handle WhatsApp DMs business"
- "stop missing customer messages"
- "Nigerian SME productivity tools"
- "Detty December bookings system" (seasonal play, Nov)
- "Lagos restaurant booking software"

**Long-tail (high intent, low competition):**
- "Mercury Lagos reservation" (and other branded venue terms — captures returnees)
- "AI for [vertical] Lagos" (5 vertical pages × 5 search terms)
- "Reservation deposit Paystack restaurant"
- "Auto reply WhatsApp Lagos"

Keyword research tool: **Ubersuggest free tier** + Google search "people also ask" boxes. Don't pay for SEMrush yet.

---

### 7. Backlink starter pack (after site is live)

- **TechCabal** — submit ReachNG for their startup roundup
- **Techpoint Africa** — same
- **BenjaminDada.com** — the African tech newsletter
- **Productpedia** / **AppSumo Africa** — startup directories
- **Lagos Startup Week** site — submit to founder directory
- **Y Combinator's Startup School directory** — free
- **Nigerian SME Hub directories** — VConnect listing for ReachNG itself, BusinessList.com.ng
- **Founder Twitter (Yori)** — reply-guy on Iyin@Paystack, Tunde@Bumpa, Olu@Flutterwave threads with thoughtful takes; eventual quote-tweet earns visibility

Each of these is ₦0 + 30 mins. Build 10 quality backlinks in week 1 of public launch.

---

## VIIBE — Mobile App, ASO Play

Different beast. App Store + Play Store optimization, not web SEO.

### Current state
- Mobile app on Expo SDK 54 (React Native)
- No App Store or Play Store listing yet (assumed pre-launch)
- No web landing page

### Highest-impact fixes
1. **App Store listing prep** — title format: "VIIBE: Lagos Scene & Vibes Finder" (60 char limit). Subtitle: "See where the energy is, tonight." (30 char). Description: 4000 chars — mention "scene rating", "live energy", "Lagos nightlife", "ages 10+", "any live experience" — front-load primary keywords in first 250 chars.
2. **Screenshots** — 5–10 per platform, captions baked in. First 3 visible without scrolling = 80% of conversion.
3. **Preview video** — 30s loop showing a scene rating in action.
4. **Web landing page at `viibe.ng` or `vibe.ng`** — single page, App Store + Play Store buttons, OG card for share. Hosted free on Vercel/Netlify. Critical for press / cold-share previews.
5. **Keywords** — App Store algorithm weights keyword field heavily. Use up to 100 chars: `lagos,nightlife,scene,vibe,events,club,rate,review,nigeria,music,party,ng`
6. **Localized listings** — submit "Nigeria" as primary region. ASO ranking is regional.

### Effort
- 1 day to nail App Store listing (writing + screenshots + video).
- 1 day for `viibe.ng` web landing page.
- Both feasible before mobile build is fully shipped — listings can be in "ready for review" state.

---

## Roomly — Separate Audit Required

Roomly lives at `C:\Users\OAJAGUN\Documents\roomly` — outside this workspace. **Cannot audit from here.**

To audit:
1. Open the Roomly repo in a fresh Claude Code session
2. Check root route, public pages, robots/sitemap, OG tags, schema, domain
3. Determine: web product (SEO) or mobile (ASO) or hybrid
4. Output `roomly/SEO_AUDIT.md`

Estimate: 1 hour once in the repo.

---

## Cross-project assets — build once, reuse

These compound across all 3 projects:

1. **Schema.org Person markup for Yori** — same JSON on each domain's About page. Builds founder-entity authority across all projects.
   ```json
   { "@type": "Person", "name": "Oluyori Ajagun",
     "jobTitle": "Founder",
     "worksFor": [
       { "@type": "Organization", "name": "ReachNG", "url": "https://reachng.ng" },
       { "@type": "Organization", "name": "VIIBE", "url": "https://viibe.ng" },
       { "@type": "Organization", "name": "Roomly", "url": "https://roomly.app" }
     ] }
   ```
2. **Footer cross-links** — each site links to the other two in the footer ("Other projects by Yori"). Internal-network signal. ₦0 effort.
3. **Shared blog stack** — one blog domain (e.g. `blog.ajagun.io`) cross-publishing thought-leadership posts. Each post links to relevant project. Cheaper than 3 blogs.
4. **Founder Twitter / LinkedIn** — single account building authority across all 3. Quote-tweets and threads about Lagos SME pain reach all audiences.

---

## Recommended sequence

**Week 1 (build foundation):**
1. Buy `reachng.ng` (or alt) — ₦15K
2. Build the marketing site on existing FastAPI/Jinja stack — 2 days
3. Add robots.txt, sitemap.xml, schema.org, OG cards — 0.5 day
4. Configure Railway custom domain — 0.5 day

**Week 2 (content + signals):**
5. Write 5 cornerstone blog posts (1 per vertical) — 2 days
6. Submit to 10 directories + reach out to TechCabal/Techpoint — 1 day
7. Set up `viibe.ng` landing page + start App Store listing prep — 1 day

**Week 3 (Roomly + amplification):**
8. Audit Roomly in its own repo — 1 hour
9. Apply same playbook to Roomly — depends on findings
10. Founder Twitter + LinkedIn cadence: 3 posts/week per project — ongoing

**Total to "ready for SEO traffic": ~2 weeks of focused work.**

---

## What NOT to do (anti-patterns)

- ❌ **Don't buy ads before the site exists.** Sending paid traffic to a 401 page is setting fire to money.
- ❌ **Don't run an "SEO campaign" via an agency.** Lagos SEO agencies charge ₦200K–₦500K/month and deliver content that sounds like 2014. Build your own founder-led content.
- ❌ **Don't write thin "5 reasons to use ReachNG" posts.** Every post must teach something concrete (e.g. "How a Lagos rooftop went from 3-hour reply time to 90 seconds — full WhatsApp transcript").
- ❌ **Don't block search engines accidentally** with `noindex` on the marketing site. Demo and admin pages, yes. Marketing pages, no.
- ❌ **Don't forget mobile.** 80%+ of Lagos search traffic is mobile. Test every page at 375px viewport before shipping.
- ❌ **Don't gate the demo portals behind email capture.** Friction kills the magic. Capture email at signup, not at demo.

---

*Logged in BACKLOG.md — promote to PLAN.md when ready to execute.*
