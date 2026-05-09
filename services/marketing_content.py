"""
Vertical-specific marketing content for /for/<vertical> landers.
One dict per vertical mirroring the demo dataset structure.
"""
from __future__ import annotations
from typing import Optional


HOSPITALITY = {
    "vertical_key": "hospitality",
    "demo_slug": "hospitality",
    "category": "Restaurants & Venues",
    "sample_brand": "Mercury Lagos",
    "headline": "Stop losing tables to slow WhatsApp replies.",
    "subhead": "Your DMs are flooded. Your guests message at 11pm. By morning they've booked your competitor. ReachNG handles every reservation enquiry in under 2 minutes — your voice, your menu, your approval before send.",
    "meta_description": "AI agent for Lagos restaurants, bars and venues. Handles reservations, takes deposits via Paystack, kills no-shows. Built for Detty December and owambe season.",
    "pain_h2": "Hospitality in Lagos is won and lost in WhatsApp.",
    "pain_sub": "The average mid-tier rooftop loses ₦1M+ a month to bookings that walked because nobody replied fast enough.",
    "pain_points": [
        {"title": "5–8 leaked bookings per week", "body": "₦40K–₦80K average ticket. Detty December multiplies inbound 4–5×. Your social media manager answers in hours, not minutes."},
        {"title": "No-show rate 18% and climbing", "body": "Without a deposit conversation upfront, the ₦450K Saturday booking ghosts. The chair sits empty. The kitchen prepped for nothing."},
        {"title": "Private events take 6 messages and 2 days", "body": "Birthdays, corporate dinners, label nights. By the time you've sent the event pack, the client has booked elsewhere."},
        {"title": "After-hours = dead", "body": "Your busiest inbound window is 9pm–midnight. Your team is closed. The agent works your hours, not theirs."},
        {"title": "Returnee December chaos", "body": "Diaspora floods back, your DMs become ungovernable, your team is on holiday. The agent doesn't take leave."},
        {"title": "Your social media manager costs more than the leak", "body": "₦200K–₦400K/month for someone who answers DMs slowly. The agent does it faster, for less, with your approval on every word."},
    ],
    "solution_h2": "An agent built for how Lagos venues actually run.",
    "solution_sub": "Reservations, events, deposits, capacity, no-show prevention, returnee surge. Vertical-aware drafts that reference Detty December, owambe, label nights — because the agent knows the difference.",
    "features": [
        {"tag": "Reservation Closer", "title": "Tables locked in 90 seconds", "body": "Agent asks party size, date, occasion. Confirms availability against your live capacity. Books, sends location pin + dress code + house rules. Customer never feels they're talking to a bot."},
        {"tag": "Event Booking Engine", "title": "Birthdays, corporate, label nights — all handled", "body": "Group qualifying + event pack PDF + 50% deposit via Paystack + date locked. The conversation that took 6 messages and 2 days, done in one back-and-forth."},
        {"tag": "Holding Reply", "title": "Instant ack, even at midnight", "body": "Customer messages at 11pm — within 1 second they get your pre-set holding message. Real reply lands minutes later. They don't ghost. They don't go to your competitor."},
        {"tag": "No-Show Killer", "title": "₦5K–₦50K deposits via Paystack", "body": "Refundable if cancelled 24h before. No-show rate drops from 18% to 3% in 30 days. Money in your bank, not promises in your DMs."},
        {"tag": "Capacity Protection", "title": "Never double-book yourself again", "body": "Set blackout dates, max group sizes, ticket caps. Agent never books past your limits. Friday rooftop full at 10:30pm → it offers Saturday alternatives."},
        {"tag": "Detty December Mode", "title": "Built for the surge", "body": "Pre-set group booking templates, waitlist management, VIP table holds for repeats, returnee priority queue. Pitch in November, ready by Dec 1."},
    ],
    "final_cta_h2": "Stop being a glorified WhatsApp typist.",
}


REAL_ESTATE = {
    "vertical_key": "real_estate",
    "demo_slug": "real-estate",
    "category": "Real Estate Agents & Developers",
    "sample_brand": "Sapphire Estates",
    "headline": "Your Saturdays back. Every viewing pre-qualified. Every PoF awkward conversation, automated.",
    "subhead": "Lagos real estate is leaked at the WhatsApp stage. Buyers DM Friday night. By Saturday morning they've contacted three competitors. ReachNG drafts every follow-up — qualifying, PoF, viewing booking — sends from your number, with your approval.",
    "meta_description": "AI sales operator for Lagos real estate agents — Banana Island, Ikoyi, Lekki, VI. Drafts buyer follow-ups, automates Proof of Funds, books viewings. ReachNG Closer.",
    "pain_h2": "You're losing ₦5M+ commission a month to slow follow-up.",
    "pain_sub": "It's not lead generation that's broken. It's the response speed. By the time you've replied, the buyer has booked elsewhere.",
    "pain_points": [
        {"title": "DMs at 9pm go unanswered till Saturday", "body": "Buyer moved on by morning. Lost commission: ₦500K–₦5M per leaked deal. Add up the leaks: it's the salary of a full-time agent."},
        {"title": "Saturdays burned on unqualified viewings", "body": "Drove to Ajah for a buyer who never had the budget. PoF was never asked. Three Saturdays a month, gone."},
        {"title": "Proof of Funds is awkward", "body": "Asking a buyer 'show me your bank statement' feels confrontational. So agents skip it. Then waste the viewing."},
        {"title": "Warm-not-ready leads ghost", "body": "Buyer says 'maybe in 6 months', and that's the end. No nurture sequence. They forget you. They buy from whoever DMs them in October."},
        {"title": "Lawyer handover is a scramble", "body": "Deal closes, then you spend 3 hours assembling the documents bundle for the lawyer. KYC scattered, C of O hunt, missing utility bill."},
        {"title": "Premium buyers expect premium response", "body": "A Banana Island buyer with USD budget will not wait 4 hours for a reply. Tier-1 leads close with whoever responds first, period."},
    ],
    "solution_h2": "ReachNG Closer is your AI sales operator.",
    "solution_sub": "Forward any inbound (DM, WhatsApp, form, referral) and the agent drafts every follow-up. You only show up to qualified viewings with PoF-cleared buyers. Your Saturdays come back.",
    "features": [
        {"tag": "Lead-to-Viewing Closer", "title": "Every DM warm-replied within minutes, 24/7", "body": "Agent qualifies, handles price objections using your brief, books the viewing into your calendar. Your voice, your pace, zero AI embarrassments."},
        {"tag": "Proof-of-Funds Concierge", "title": "Automate the awkward conversation", "body": "Agent requests PoF politely at the right stage. Reviews bank statement summary, flags red flags (round-number deposits, no transaction history). Only escalates qualified buyers."},
        {"tag": "Nurture Loop", "title": "Warm-not-ready leads stay warm", "body": "Buyers who aren't ready this month get dripped useful updates — new comparable listings, market notes, neighbourhood news. When they say 'I'm ready now', you hear about it first."},
        {"tag": "KYC Vault", "title": "NIN, passport, utility bill — extracted, filed, searchable", "body": "Upload a doc, Claude Vision pulls every field, files in a vault per buyer. Ready for your lawyer in one click."},
        {"tag": "Lawyer Handover Bundle", "title": "Closing day takes 5 minutes", "body": "Agent generates the formal handover memo (parties, price, Land Use Act flags, Governor's Consent status, red flags) and zips the document bundle. No scramble."},
        {"tag": "Neighborhood Scorecard", "title": "Close faster with Lagos-specific intel", "body": "For any address, instant scorecard: commute time to VI/Ikoyi/Ikeja at 8am peak, nearby amenities, flood-risk rating. Share with buyers to remove objections."},
    ],
    "final_cta_h2": "Get your Saturdays back.",
}


EDUCATION = {
    "vertical_key": "education",
    "demo_slug": "school",
    "category": "Schools & Lesson Centres",
    "sample_brand": "Lagoon British International",
    "headline": "Admissions enquiries answered in minutes — not Monday.",
    "subhead": "Diaspora parents email Friday evening asking for the prospectus. By Monday morning, three competitor schools have already replied. ReachNG keeps your admissions inbox at zero, every day.",
    "meta_description": "AI admissions assistant for Lagos schools. Handles prospectus requests, tour bookings, fee enquiries 24/7. Speaks parents' language — relocations, scholarships, year-group fit.",
    "pain_h2": "Admissions die in WhatsApp inboxes.",
    "pain_sub": "The school that replies fastest wins the registration. Today, that's not you.",
    "pain_points": [
        {"title": "Diaspora enquiries go unanswered", "body": "Parents in London/Houston/Atlanta message 11pm Lagos time. Your admissions team logs in at 8am. Window closed."},
        {"title": "Generic fee replies undersell you", "body": "'Send me the fee structure' gets a PDF and silence. No qualifying. No tour offer. No follow-up. The relationship dies."},
        {"title": "Tours don't get booked", "body": "Family says 'we'll come visit', and that's the last you hear. No calendar slot. No reminder. They visit your competitor instead."},
        {"title": "Scholarship enquiries fall through", "body": "High-performing students email about scholarships. Your admissions desk doesn't know how to reply quickly. They go to the school that did."},
        {"title": "Returning families lose touch", "body": "Year 6 parents asking about Year 7 transition deserve a warm, personalised response. They get a copy-paste."},
        {"title": "Fee chase is awkward", "body": "Late fee reminders feel impolite. So they don't get sent. Term begins, students show up, fees unpaid, awkward all round."},
    ],
    "solution_h2": "An agent that runs admissions like a senior registrar.",
    "solution_sub": "Prospectus requests, tour bookings, fee chase, scholarship pipeline, transition enquiries — handled in your tone, with the qualifying questions a real registrar would ask.",
    "features": [
        {"tag": "Admissions Closer", "title": "Every enquiry handled in under 4 minutes", "body": "Agent sends prospectus + fee schedule + tour offer + asks qualifying questions (year group, current school, relocation timeline). One reply, full context."},
        {"tag": "Tour Booking Engine", "title": "Calendar-locked, reminded, confirmed", "body": "Family asks 'can we visit?' — agent offers slots, locks in calendar, sends confirmation + parking + dress code. Auto-reminder 24h before."},
        {"tag": "Scholarship Pipeline", "title": "High-performers don't slip through", "body": "Scholarship enquiries auto-routed to the Admissions Director, with full context: latest reports, references, fit assessment. Faster decisions."},
        {"tag": "Diaspora-Aware Drafting", "title": "Built for international parents", "body": "Agent recognises London/Atlanta/Toronto context. Asks about relocation timeline, school year alignment, video tour preference. Lands the family before they land in Lagos."},
        {"tag": "Fee Chase, Politely", "title": "Term-start cashflow, automated", "body": "Friendly term-1 reminders, escalating tone, payment plan offer where appropriate. Never impolite, always clear. Cashflow up, awkwardness down."},
        {"tag": "Year-Group Transition", "title": "Existing parents nurtured", "body": "Year 6 to Year 7 transition, sixth form decisions, sibling enrolment — agent maintains the relationship with current parents through every stage."},
    ],
    "final_cta_h2": "Keep admissions at zero. Every day.",
}


PROFESSIONAL_SERVICES = {
    "vertical_key": "professional_services",
    "demo_slug": "legal",
    "category": "Legal & Professional Firms",
    "sample_brand": "Adesina & Co. Solicitors",
    "headline": "Your Friday-evening enquiry answered before Monday morning.",
    "subhead": "Retainer-sized clients email after hours. By the time your office opens, they've hired your competitor. ReachNG triages every cold enquiry, qualifies the matter, and books the consultation — all from your firm's voice.",
    "meta_description": "AI client intake for Lagos law firms, accountants, consultants. Triages enquiries, qualifies matters, books paid consultations. Confidentiality-aware, conflict-checked.",
    "pain_h2": "After-hours enquiries are where retainers walk.",
    "pain_sub": "The discerning client that emailed Friday at 6pm has hired your competitor by Tuesday. Speed is the differentiator.",
    "pain_points": [
        {"title": "Cold enquiries die over the weekend", "body": "₦8M retainer client emails Friday 6pm. Office opens Monday 9am. They've already engaged Banwo & Ighodalo by Sunday."},
        {"title": "Junior associates triage badly", "body": "Senior matters routed to wrong partners. Wrong tone in early correspondence. Loses the case before it starts."},
        {"title": "Consultation fees never get collected", "body": "'Initial consultation' becomes a 90-minute giveaway. Then the client ghosts. ₦300K of partner time, gone."},
        {"title": "Conflict checks happen too late", "body": "Engagement letter drafted, then someone realises Adekoya v. Bank PHB is on file. Awkward retraction. Damaged reputation."},
        {"title": "Document review takes too long", "body": "Mrs Folorunsho's land case sits on a partner's desk for 2 weeks because nobody flagged urgency. She moves to a faster firm."},
        {"title": "Repeat clients undervalue you", "body": "No nurture between matters. A great M&A client forgets you for their next acquisition. They google, find a competitor, retain them."},
    ],
    "solution_h2": "An agent that runs intake like a senior client services partner.",
    "solution_sub": "Triages every enquiry, qualifies the matter, quotes the consultation fee, books the call. Conflict-aware, confidentiality-trained, never makes legal claims it shouldn't.",
    "features": [
        {"tag": "Client Intake Closer", "title": "Every cold enquiry replied in 6 minutes", "body": "Agent identifies practice area, qualifies urgency, quotes the consultation fee, books the call. Confidentiality assured upfront."},
        {"tag": "Practice-Area Routing", "title": "Right partner, right matter", "body": "M&A goes to the corporate partner. Land disputes to property. Employment to the litigation team. Auto-routed with full context."},
        {"tag": "Consultation Fee Engine", "title": "₦150K–₦500K paid before the call", "body": "Agent quotes the fee, sends Paystack link, locks the slot only after payment. No more 90-minute giveaways."},
        {"tag": "Conflict-Check Flag", "title": "Catches conflicts before engagement", "body": "Agent cross-references the prospect against active matters, flags potential conflicts before any commitment. Reputation-protective."},
        {"tag": "Matter Pipeline", "title": "Every active file in one view", "body": "Discovery, pleadings, mediation, drafting, submission — every matter's stage visible. Next-action reminders for partners."},
        {"tag": "Nurture Loop for Past Clients", "title": "M&A client doesn't forget you", "body": "Quarterly check-ins, regulatory update emails, deal-relevant news. The next acquisition naturally comes back to you."},
    ],
    "final_cta_h2": "Stop losing retainers to faster firms.",
}


SMALL_BUSINESS = {
    "vertical_key": "small_business",
    "demo_slug": "smb",
    "category": "Beauty, Wellness & Small Businesses",
    "sample_brand": "Glow Studio Lagos",
    "headline": "From 142 DMs a week to 0 missed bookings.",
    "subhead": "Beauty, wellness, fitness, small services — your IG DMs are flooded, your bookings calendar is chaos, no-shows eat your weekends. ReachNG handles every booking, takes every deposit, kills the no-show problem.",
    "meta_description": "AI booking agent for Lagos beauty studios, salons, gyms, wellness brands. Handles IG DMs, takes Paystack deposits, eliminates no-shows.",
    "pain_h2": "Your IG is a goldmine you can't dig up.",
    "pain_sub": "The customers are messaging. The bookings are walking. The chair sits empty Saturday afternoon. It's not a marketing problem — it's a response-and-deposit problem.",
    "pain_points": [
        {"title": "142 DMs a week, half unanswered", "body": "Every hour you spend in the chair is another 20 DMs unread. You catch up at 11pm, half the customers are gone."},
        {"title": "No-show rate 18%", "body": "Saturday afternoon, the chair is empty. Customer 'forgot'. No deposit was taken. You can't fill the slot last-minute."},
        {"title": "Pricing questions become free advice", "body": "'How much for a full set?' becomes a 20-message back-and-forth. The customer never books. You typed for nothing."},
        {"title": "Returning customers stop returning", "body": "No follow-up after appointment. No 'time for your fill-in?' nudge. They forget. They go to the salon that DMs them every 4 weeks."},
        {"title": "Bridal squads vanish", "body": "₦320K group booking enquiry comes in. By the time you've sent the package details, they've booked elsewhere."},
        {"title": "You're answering DMs at 1am", "body": "Your sleep, your weekend, your sanity — all eaten by WhatsApp."},
    ],
    "solution_h2": "An agent built for IG-first, deposit-now Lagos businesses.",
    "solution_sub": "Bookings, deposits, follow-up nudges, group packages, returning-customer loyalty — all handled in your brand's voice. Including the emoji.",
    "features": [
        {"tag": "Booking Closer", "title": "Every DM converts in 5 minutes", "body": "Agent asks service, day, time, first-visit-or-regular. Confirms availability, sends Paystack deposit link, locks the slot. Done."},
        {"tag": "Deposit Engine", "title": "No deposit, no booking", "body": "₦5K–₦15K refundable deposit on every appointment via Paystack. No-show rate drops from 18% to 4% in 30 days."},
        {"tag": "Group & Bridal Packages", "title": "Bridal squad bookings, locked", "body": "Group qualifying, package PDF, group deposit (refundable up to 48h). Bookings that took 6 messages, done in one back-and-forth."},
        {"tag": "Returning-Customer Loop", "title": "'Time for your fill-in?' nudges", "body": "4-week, 6-week, 8-week service-specific reminders. The customer who'd have forgotten you, comes back. Loyalty as a feature."},
        {"tag": "Pricing Q&A Triage", "title": "Pricing questions handled instantly", "body": "Pre-built price card per service. Agent answers in 1 message, then asks 'shall I lock you in?' The 20-message back-and-forth disappears."},
        {"tag": "Late-Night Holding Reply", "title": "1am DMs get instant ack", "body": "Customer messages at midnight, gets your pre-set holding reply within 1 second. Real reply lands first thing in the morning. They don't ghost."},
    ],
    "final_cta_h2": "Get your sleep back.",
}


CONTENT: dict[str, dict] = {
    "hospitality":           HOSPITALITY,
    "real_estate":           REAL_ESTATE,
    "education":             EDUCATION,
    "professional_services": PROFESSIONAL_SERVICES,
    "small_business":        SMALL_BUSINESS,

    # Friendly URL aliases used in the marketing nav and footer
    "restaurants": HOSPITALITY,
    "real-estate": REAL_ESTATE,
    "schools":     EDUCATION,
    "legal":       PROFESSIONAL_SERVICES,
    "smb":         SMALL_BUSINESS,
    "small-business": SMALL_BUSINESS,
}


def get_vertical_content(slug: Optional[str]) -> Optional[dict]:
    if not slug:
        return None
    return CONTENT.get(slug.lower().replace("_", "-"))


def list_canonical_slugs() -> list[str]:
    """Slugs used in the public marketing URLs (with hyphens)."""
    return ["restaurants", "real-estate", "schools", "legal", "small-business"]
