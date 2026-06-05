# EYO Channels & Meta Integration — Reference

How EYO expands beyond WhatsApp, and exactly what the Meta IG/Facebook path
requires (App Review, Business Verification, CAC). Written so future-you doesn't
re-derive it.

Last updated: 2026-06-06

---

## 1. The core idea: one brain, many channels

EYO's value is the **owner-side brain** — draft in the owner's voice, catch the
money, remember the customer, HITL (nothing sends without a tap). **That brain is
channel-agnostic.** A channel is just a *transport adapter* that:

1. normalizes inbound (a message / email) → the brain, and
2. sends the brain's approved reply back out.

So adding a channel ≈ adding an adapter. The inventions (Radar, Money-Leak,
Cashflow, Shield, Referral) and the 7am Owner Brief all get **richer** with every
channel, because they see more signal. The moat is: **one brain, one brief, one
unified customer across every inbox.**

---

## 2. Channel-by-channel

| Channel | Transport | Status | Gate |
|---|---|---|---|
| **WhatsApp** | Unipile (per-client QR pairing) | **Live** | None — client pairs their own number |
| **WhatsApp (official tier)** | Meta WhatsApp Cloud API | Optional/fallback | Meta App + (eventually) business verification |
| **Email** | Unipile (Gmail/Outlook hosted-auth) | **Built (Phase 1–2)** | None — client connects their own mailbox |
| **Instagram DM** | **Meta** (Instagram Messaging API) | Planned | Meta App Review + Business Verification |
| **Facebook Messenger** | **Meta** (Messenger Platform) | Planned | Meta App Review + Business Verification |
| **TikTok** | — | **Not viable** as a conversation channel | No business DM API; ToS-risky. Use as a lead/content source only |

**Why Meta (not Unipile) for IG + Messenger:** they run on the *same* Meta
infrastructure as WhatsApp Cloud API — one Meta App, one webhook endpoint (branch
on `object`/`field`), one Graph API send. It's the official, ban-safe, ToS-clean
path and it reuses the Meta scaffolding ReachNG already has (`META_APP_SECRET`,
webhook HMAC verification, the Meta send path). It also reinforces the positioning:
**EYO works *alongside* Meta, on Meta's own rails.**

**Why Unipile for email:** Meta doesn't do email. Unipile already supports
Gmail/Outlook via the same hosted-auth flow we use for WhatsApp.

---

## 3. The Meta gate — read this carefully

### "ReachNG isn't an app, how do I submit it?"

A **"Meta App"** is **not** a mobile/installed app. It's a **developer project**
you register on `developers.facebook.com` to get an App ID + secret and call
Meta's APIs. Any website or backend that talks to Meta is an "app" in their sense.

**You already have one** — the WhatsApp Cloud API integration uses
`META_APP_SECRET` / `META_PHONE_NUMBER_ID` / `META_ACCESS_TOKEN`, which come from
an existing Meta App. "App Review" = in that dashboard → App Review → request the
IG/Messenger permissions → upload a **screencast** of EYO using them → submit. A
web form + a screen recording. **Not** an app-store submission.

### You go through it ONCE. Your clients never do.

App Review + Business Verification is on **your** app, done **one time, by you**.
Once approved, **any** business connects in ~30 seconds with no review.

- **ReachNG (once, upfront):**
  1. **Business Verification** — prove ReachNG is a real business to Meta (CAC
     docs). May be partly done already from the WhatsApp path.
  2. **App Review** — request the messaging permissions
     (`instagram_manage_messages`, `pages_messaging`, `instagram_basic`),
     screencast, submit. Once per permission.
- **Each client (every time, frictionless):** tap "Connect Instagram / Facebook"
  → Facebook Login → "Allow" → done. No review, no paperwork. Like "Sign in with
  Google." Same shape as the WhatsApp/email pairing.

### You can pilot BEFORE review finishes

Until the app passes review it's in **Development Mode / Standard Access**, which
still works for accounts that have a **role on the app** (you + anyone added as a
"tester"). So you can **build, demo, and run a real pilot** with a hand-added
pilot client's IG/Page *before* public review. Full review only opens it to *any*
business self-serve.

> **Model: one front-loaded review for you → unlimited frictionless client
> connections.** The friction lands on you once; client onboarding stays a tap.

### The 24-hour window (separate from review)

A messaging **policy**, not a gate: within 24h of a customer messaging the
business, EYO replies freely; outside 24h you need approved templates/tags. EYO
is reply-centric, so it lives inside the window. Automatic.

---

## 4. The actual blocker: CAC registration

**Business Verification needs a legally registered business.** In Nigeria that's
**CAC registration** (RC number, name). Without it you cannot complete Business
Verification → cannot get production access to the IG/Messenger permissions.

Sequence for the Meta IG/FB track:

1. **Register ReachNG with CAC** (Corporate Affairs Commission, online portal,
   modest cost, ~a couple of weeks). Business Name *or* Limited Company both work.
2. → **Business Verification** on Meta (submit CAC docs).
3. → **App Review** for the IG/Messenger permissions.
4. → production, self-serve client connections.

CAC is worth doing anyway — business bank account, contracts, Paystack, trust.

---

## 5. What's blocked vs not (the important part)

**Your immediate path needs ZERO Meta verification and ZERO CAC:**

- **WhatsApp via Unipile** — each client pairs their *own* WhatsApp by QR. No Meta
  App, no verification.
- **Email via Unipile** — client connects their *own* mailbox. Same.

So you can **land the first Lagos client and run EYO on WhatsApp + email today**,
with no CAC and no Meta review. **Meta IG/FB is a later expansion** unlocked once
ReachNG is CAC-registered — kick it off in parallel, in the background, while the
product earns its first revenue.

**Bottom line:** CAC + Meta review gate only the *Meta IG/FB channel*, never the
wedge. Don't let them block shipping.

---

## 6. Action checklist

- [ ] (Background) Start **CAC registration** for ReachNG — unblocks everything Meta.
- [ ] Land first Lagos client on **WhatsApp + email (Unipile)** — needs none of the above.
- [ ] Once CAC done → **Business Verification** on the existing Meta App.
- [ ] Build the **Meta IG + Messenger adapter** (reuses the Meta App + webhook); pilot in Dev Mode with a tester account.
- [ ] Submit **App Review** for `instagram_manage_messages` / `pages_messaging`.
- [ ] Flip IG/FB to production self-serve.
