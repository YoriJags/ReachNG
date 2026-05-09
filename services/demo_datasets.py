"""
Demo datasets for the public pitch portal at `/portal/demo/<vertical>`.

Each vertical returns a dict the template renders verbatim — no live DB.
Used for prospects to see themselves in the product within 5 seconds.

Add a new vertical: drop a key into DATASETS, mirror the shape of an existing
entry, and route `/portal/demo/<key>` will work automatically.
"""
from __future__ import annotations
from typing import Optional

# Each entry's shape:
# {
#   "brand": str,                  # client name in hero
#   "tagline": str,                # one-line eyebrow under hero
#   "category": str,               # shows in topbar pill
#   "stats": [                     # exactly 4 stat cards
#       {"label": str, "value": str, "value_num": float, "value_prefix": str, "value_suffix": str, "change": str, "tone": "orange"|"green"|"gold"|"blue"},
#       ...
#   ],
#   "hitl_section_label": str,     # e.g. "Pending Approval"
#   "hitl_drafts": [               # 3 drafts awaiting approval
#       {"name": str, "initials": str, "time": str, "tag": str, "tag_label": str, "inbound": str, "draft": str},
#       ...
#   ],
#   "secondary_section": Optional[dict],  # vertical-specific extra section (capacity for hospitality, viewings for estate, etc.)
#       # {"title": str, "type": "capacity_grid"|"none", "data": [...]}
#   "activity_label": str,
#   "activity": [{"type": "confirmed"|"replied"|"sent", "text": str, "time": str}],
#   "pipeline_label": str,
#   "pipeline_columns": [str, str, str, str, str],
#   "pipeline": [{"col1": str, "col2": str, "col3": str, "status": str, "col5": str}],
#   "holding_message": str,        # pre-filled holding reply demo
#   "intro_label": str,            # e.g. "Reservation & Events Inbox" — under hero
# }


HOSPITALITY = {
    "brand": "Mercury Lagos",
    "tagline": "Rooftop Bar & Lounge · Victoria Island",
    "category": "Hospitality",
    "intro_label": "Reservation & Events Inbox",
    "stats": [
        {"label": "Enquiries This Week", "value_num": 34, "value_prefix": "", "value_suffix": "", "change": "WhatsApp inbound handled", "tone": "orange"},
        {"label": "Bookings Confirmed",  "value_num": 18, "value_prefix": "", "value_suffix": "", "change": "Tables & events closed", "tone": "green"},
        {"label": "Revenue Tracked",     "value_num": 2.4, "value_prefix": "₦", "value_suffix": "M", "change": "from confirmed bookings", "tone": "gold"},
        {"label": "Avg. Response Time",  "value_num": 2,  "value_prefix": "", "value_suffix": " min", "change": "Was 3+ hours", "tone": "blue"},
    ],
    "hitl_section_label": "Pending Approval",
    "hitl_drafts": [
        {"name": "Tunde Adeyemi", "initials": "TA", "time": "8 minutes ago", "tag": "reservation", "tag_label": "Table Booking",
         "inbound": "Hi, do you have space for 4 people this Saturday? What's the vibe like and is there a minimum spend?",
         "draft": "Hi Tunde! Yes, we have availability for 4 on Saturday from 8pm onwards. Our rooftop is lively with a DJ set from 10pm — great energy. Minimum spend is ₦50,000 per table, which covers drinks and small plates. Shall I hold a table for you? I'll just need a name and a quick confirmation."},
        {"name": "Chisom Okafor", "initials": "CO", "time": "23 minutes ago", "tag": "event", "tag_label": "Birthday Event",
         "inbound": "Good evening. I want to plan a birthday dinner for about 25 people next month. Do you do private sections? What's the process?",
         "draft": "Good evening Chisom! We'd love to host your birthday celebration at Mercury. We have a private section on the rooftop that accommodates up to 35 guests with a dedicated bar area and stunning Lagos skyline views.\n\nFor private bookings of 25 guests, our minimum spend is ₦500,000 which includes a welcome drinks round, table service, and your own playlist slot with the DJ.\n\nTo secure the date, we'd need a 50% deposit. What date were you considering? I can check availability and send you a full proposal."},
        {"name": "Emeka Nwosu", "initials": "EN", "time": "41 minutes ago", "tag": "enquiry", "tag_label": "Corporate Event",
         "inbound": "We're looking for a venue for a corporate team outing, around 40 people, cocktails and dinner. Do you cater for that sort of thing?",
         "draft": "Hi Emeka, Mercury is a great fit for corporate events — we've hosted several team outings and client dinners on the rooftop. For 40 guests we'd recommend a full private hire or a semi-private section depending on the evening.\n\nFull hire is available on weeknights and includes: full bar, canapés and sharing platters, dedicated host, and PA system if needed. Pricing starts from ₦1.2M for the space.\n\nWould a weeknight work for your team? I can walk you through the options and send a formal proposal."},
    ],
    "secondary_section": {
        "title": "Venue Capacity — This Week",
        "type": "capacity_grid",
        "data": [
            {"day": "Mon", "date": "6 May",  "pct": 0,   "status": "closed", "note": "Closed"},
            {"day": "Tue", "date": "7 May",  "pct": 35,  "status": "open",   "note": "Plenty of space"},
            {"day": "Wed", "date": "8 May",  "pct": 60,  "status": "busy",   "note": "Corporate mixer (20 pax)"},
            {"day": "Thu", "date": "9 May",  "pct": 45,  "status": "open",   "note": "Moderate — walk-ins welcome"},
            {"day": "Fri", "date": "10 May", "pct": 88,  "status": "busy",   "note": "Filling fast — 2 events in"},
            {"day": "Sat", "date": "11 May", "pct": 100, "status": "full",   "note": "Birthday takeover — private"},
            {"day": "Sun", "date": "12 May", "pct": 20,  "status": "open",   "note": "Open — light night"},
        ],
    },
    "activity_label": "Recent Activity",
    "activity": [
        {"type": "confirmed", "text": "<strong>Funke Balogun</strong> — Birthday takeover for 30 confirmed. ₦450,000 min spend. DJ slot secured.", "time": "1 hour ago"},
        {"type": "replied",   "text": "<strong>David Eze</strong> — Asked about bottle service options for Saturday. ReachNG sent the full menu.", "time": "2 hours ago"},
        {"type": "confirmed", "text": "<strong>Kemi Adebayo</strong> — Corporate mixer for 20, Thursday night. ₦380,000 confirmed.", "time": "3 hours ago"},
        {"type": "sent",      "text": "<strong>Seun Oladipo</strong> — Enquiry received at 11:43pm. ReachNG replied in 90 seconds.", "time": "4 hours ago"},
        {"type": "confirmed", "text": "<strong>Tobenna Obi</strong> — VIP table for 6, Saturday 10pm. ₦90,000 confirmed.", "time": "5 hours ago"},
        {"type": "replied",   "text": "<strong>Amaka Igwe</strong> — Asked about hosting a label event. ReachNG qualified and escalated to you.", "time": "6 hours ago"},
    ],
    "pipeline_label": "Reservation Pipeline",
    "pipeline_columns": ["Guest / Enquiry", "Type", "Details", "Status", "Last Touch"],
    "pipeline": [
        {"col1": "Funke Balogun",    "col2": "Birthday Takeover",  "col3": "30 guests · Sat 10 May · ₦450K",  "status": "confirmed", "col5": "1 hour ago"},
        {"col1": "Kemi Adebayo",     "col2": "Corporate Mixer",    "col3": "20 guests · Thu 8 May · ₦380K",   "status": "confirmed", "col5": "3 hours ago"},
        {"col1": "Tobenna Obi",      "col2": "VIP Table",          "col3": "6 guests · Sat 10 May · ₦90K",    "status": "confirmed", "col5": "5 hours ago"},
        {"col1": "Tunde Adeyemi",    "col2": "Table Booking",      "col3": "4 guests · Sat 10 May",            "status": "pending",   "col5": "8 mins ago"},
        {"col1": "Chisom Okafor",    "col2": "Birthday Event",     "col3": "25 guests · TBC",                  "status": "pending",   "col5": "23 mins ago"},
        {"col1": "Emeka Nwosu",      "col2": "Corporate Event",    "col3": "40 guests · TBC",                  "status": "replied",   "col5": "41 mins ago"},
        {"col1": "Amaka Igwe",       "col2": "Label Night Enquiry","col3": "50+ guests · TBC",                 "status": "replied",   "col5": "6 hours ago"},
        {"col1": "Seun Oladipo",     "col2": "Table Booking",      "col3": "3 guests · Sun 11 May",            "status": "new",       "col5": "4 hours ago"},
    ],
    "holding_message": "Hi! Thanks for reaching out to Mercury — give us a few minutes and we'll be back with availability, pricing and the vibe for the night. 🥂",
}


REAL_ESTATE = {
    "brand": "Sapphire Estates",
    "tagline": "Luxury Real Estate · Banana Island & Ikoyi",
    "category": "Real Estate",
    "intro_label": "Buyer Enquiries & Viewing Inbox",
    "stats": [
        {"label": "Enquiries This Week", "value_num": 47, "value_prefix": "", "value_suffix": "", "change": "Active buyers handled", "tone": "orange"},
        {"label": "Viewings Booked",     "value_num": 12, "value_prefix": "", "value_suffix": "", "change": "Confirmed walk-throughs", "tone": "green"},
        {"label": "Pipeline Value",      "value_num": 4.8, "value_prefix": "₦", "value_suffix": "B", "change": "in qualified pipeline", "tone": "gold"},
        {"label": "Avg. Response Time",  "value_num": 3,  "value_prefix": "", "value_suffix": " min", "change": "Was next-day", "tone": "blue"},
    ],
    "hitl_section_label": "Pending Approval",
    "hitl_drafts": [
        {"name": "Adaeze Onuoha", "initials": "AO", "time": "12 minutes ago", "tag": "viewing", "tag_label": "Viewing Request",
         "inbound": "Hi, I saw the 5-bed in Banana Island on your IG. Is it still available? Can I view this weekend?",
         "draft": "Hi Adaeze, the 5-bed waterfront duplex on Banana Island is still available — ₦650M, fully serviced, private jetty. We have viewing slots Saturday 11am, 2pm and 4pm. Could you share a Proof of Funds before the viewing? It's standard for properties at this tier and helps us hold the slot. I can send the property pack and viewing form now."},
        {"name": "Dr Bola Adekunle", "initials": "BA", "time": "34 minutes ago", "tag": "qualifying", "tag_label": "Buyer Qualifying",
         "inbound": "Good afternoon. I'm relocating from Houston in August. Looking for a 4-5 bed in Ikoyi, ideally with a pool. Budget around $1.5M USD. What do you have?",
         "draft": "Good afternoon Dr Adekunle, welcome back. We have three properties matching that brief: a 4-bed townhouse on Bourdillon ($1.4M, completed 2025), a 5-bed standalone on Glover ($1.8M, pool, 24hr power), and a 4-bed penthouse at Old Ikoyi Club ($1.2M, harbour view). Given your August timeline I'd recommend we lock viewings now — sellers in this segment move fast. Are you in Lagos in June for a viewing trip, or shall we do a video walk-through first?"},
        {"name": "Tope Bankole", "initials": "TB", "time": "1 hour ago", "tag": "investor", "tag_label": "Investor Enquiry",
         "inbound": "I've got ₦400M to deploy. Looking for short-let-ready apartments, Ikoyi or VI. Can you put together 3 options with projected ROI?",
         "draft": "Hi Tope, that's a sweet spot for short-let returns. Three options in your range:\n\n1. 3-bed on Alexander Avenue, Ikoyi — ₦380M, fully furnished, currently letting at $250/night (≈18% gross yield).\n2. 4-bed serviced apartment, Eko Atlantic — ₦420M, pool + gym + 24hr concierge (≈22% projected gross).\n3. 2-bed waterfront, Banana Island — ₦395M, premium short-let zone (≈19% gross).\n\nWant me to send the full ROI breakdown PDFs and book viewings for all three this week?"},
    ],
    "secondary_section": {
        "title": "This Week's Viewings",
        "type": "viewings_list",
        "data": [
            {"day": "Tue 7 May",  "property": "5-bed waterfront, Banana Island", "buyer": "Mr & Mrs Eze", "status": "confirmed"},
            {"day": "Wed 8 May",  "property": "Penthouse, 1004 Estate, VI",      "buyer": "Adaeze Onuoha", "status": "tentative"},
            {"day": "Thu 9 May",  "property": "4-bed townhouse, Old Ikoyi",      "buyer": "Mr Olaniyan",   "status": "confirmed"},
            {"day": "Fri 10 May", "property": "Land, Eko Atlantic Phase 4",      "buyer": "DiasporaInvest LLC", "status": "confirmed"},
            {"day": "Sat 11 May", "property": "5-bed standalone, Glover Rd",     "buyer": "Dr Adekunle",   "status": "tentative"},
        ],
    },
    "activity_label": "Recent Activity",
    "activity": [
        {"type": "confirmed", "text": "<strong>Mr & Mrs Eze</strong> — PoF cleared. Saturday viewing for the 5-bed Banana Island property locked in.", "time": "30 mins ago"},
        {"type": "replied",   "text": "<strong>Folake Adesina</strong> — Asked about service charges on Eko Atlantic apartment. ReachNG sent the full schedule.", "time": "1 hour ago"},
        {"type": "confirmed", "text": "<strong>DiasporaInvest LLC</strong> — Bid accepted: ₦1.2B for the 4-bed waterfront. Lawyer bundle dispatched.", "time": "2 hours ago"},
        {"type": "sent",      "text": "<strong>Tope Bankole</strong> — Investor enquiry received. ReachNG qualified and replied with 3 ROI options in 4 minutes.", "time": "1 hour ago"},
        {"type": "replied",   "text": "<strong>Mrs Onyeka</strong> — KYC docs received and verified. ReachNG flagged one missing utility bill — chasing.", "time": "3 hours ago"},
        {"type": "confirmed", "text": "<strong>Hon Ibrahim Musa</strong> — Viewing pack sent + private viewing scheduled. PoF on file.", "time": "4 hours ago"},
    ],
    "pipeline_label": "Buyer Pipeline",
    "pipeline_columns": ["Buyer", "Looking For", "Budget", "Status", "Last Touch"],
    "pipeline": [
        {"col1": "Mr & Mrs Eze",        "col2": "5-bed Banana Island",     "col3": "₦650M",          "status": "confirmed", "col5": "30 mins ago"},
        {"col1": "DiasporaInvest LLC",  "col2": "4-bed waterfront",        "col3": "₦1.2B",          "status": "confirmed", "col5": "2 hours ago"},
        {"col1": "Hon Ibrahim Musa",    "col2": "Penthouse, VI",           "col3": "₦400M",          "status": "confirmed", "col5": "4 hours ago"},
        {"col1": "Adaeze Onuoha",       "col2": "5-bed Banana Island",     "col3": "TBC",            "status": "pending",   "col5": "12 mins ago"},
        {"col1": "Dr Bola Adekunle",    "col2": "4-5 bed Ikoyi",           "col3": "$1.5M USD",      "status": "pending",   "col5": "34 mins ago"},
        {"col1": "Tope Bankole",        "col2": "Short-let apartments",    "col3": "₦400M",          "status": "replied",   "col5": "1 hour ago"},
        {"col1": "Folake Adesina",      "col2": "3-bed Eko Atlantic",      "col3": "₦220M",          "status": "replied",   "col5": "1 hour ago"},
        {"col1": "Mrs Onyeka",          "col2": "4-bed Old Ikoyi",         "col3": "₦480M",          "status": "new",       "col5": "3 hours ago"},
    ],
    "holding_message": "Hello! Thanks for reaching out to Sapphire Estates. We'll be right back with full property details, pricing, and viewing slots. While you wait, please have your Proof of Funds ready — it speeds up viewing approval for our luxury inventory.",
}


EDUCATION = {
    "brand": "Lagoon British International School",
    "tagline": "Pre-K to Year 13 · Lekki Phase 1 Campus",
    "category": "Education",
    "intro_label": "Admissions & Parent Inbox",
    "stats": [
        {"label": "Admissions Enquiries", "value_num": 89, "value_prefix": "", "value_suffix": "", "change": "This term", "tone": "orange"},
        {"label": "School Tours Booked",  "value_num": 31, "value_prefix": "", "value_suffix": "", "change": "Families visited", "tone": "green"},
        {"label": "Pipeline Value",       "value_num": 240, "value_prefix": "₦", "value_suffix": "M", "change": "in fees pipeline", "tone": "gold"},
        {"label": "Avg. Response Time",   "value_num": 4,  "value_prefix": "", "value_suffix": " min", "change": "Was same-day at best", "tone": "blue"},
    ],
    "hitl_section_label": "Pending Approval",
    "hitl_drafts": [
        {"name": "Mrs Adeleke", "initials": "MA", "time": "15 minutes ago", "tag": "admissions", "tag_label": "Year 7 Admissions",
         "inbound": "Hello, I'm interested in admission for my daughter into Year 7 for September. Could you send the prospectus and fee structure?",
         "draft": "Good afternoon Mrs Adeleke, thank you for considering Lagoon British. For Year 7 entry in September, our process is: prospectus + fee schedule (sent now), entrance assessment (CAT4, online or on-campus), interview with the Head of Year, then offer. Year 7 fees for 2026/27 are ₦8.4M per term inclusive of meals, books and one extracurricular. We have an open day this Saturday at 10am — shall I reserve two spaces for you and your daughter? I'll send the prospectus and registration link now."},
        {"name": "Dr & Mrs Okonkwo", "initials": "DO", "time": "42 minutes ago", "tag": "tour", "tag_label": "School Tour Request",
         "inbound": "We're moving back from London in August. Two children — 9 and 14. Need to visit the school next time we're in Lagos (May 18-25). What's your availability?",
         "draft": "Welcome back, Dr & Mrs Okonkwo. We'd love to host you on campus during your visit. Available tour slots between 18-25 May: Mon 19th 10am, Tue 20th 2pm, Thu 22nd 11am, Fri 23rd 10am. Tours run 90 minutes and include meeting with the relevant Heads of Year (Year 5 and Year 10 for your children). I'd recommend bringing your children if their schedule allows — Year 10 entrants particularly benefit from sitting in a class. Which slot works best?"},
        {"name": "Mr Ojo", "initials": "MO", "time": "1 hour ago", "tag": "scholarship", "tag_label": "Scholarship Enquiry",
         "inbound": "My son just topped his class at his current school. Do you offer academic scholarships? He's coming into Year 10.",
         "draft": "Congratulations, Mr Ojo. Yes, we offer the Founders' Scholarship for Year 10–11 entry covering 30%, 50% or 100% of fees based on entrance assessment + portfolio. Application requires: latest two school reports, headteacher reference, and the standard CAT4 + subject papers. Deadline for September 2026 entry is 15 June. I'll send the scholarship pack and application form. Strongly recommend the on-campus assessment day on 1 June where shortlisted candidates do all components in one visit."},
    ],
    "secondary_section": {
        "title": "Open Days & Tours — This Month",
        "type": "tours_list",
        "data": [
            {"day": "Sat 11 May", "type": "Open Day (all years)",      "registered": "47 families", "status": "confirmed"},
            {"day": "Mon 13 May", "type": "Sixth Form Info Evening",   "registered": "23 families", "status": "confirmed"},
            {"day": "Wed 15 May", "type": "Pre-K Toddler Visit",       "registered": "18 families", "status": "confirmed"},
            {"day": "Thu 16 May", "type": "Year 7 Taster Day",         "registered": "31 students", "status": "confirmed"},
            {"day": "Sat 25 May", "type": "Open Day (Years 7-13)",     "registered": "12 families", "status": "filling"},
        ],
    },
    "activity_label": "Recent Activity",
    "activity": [
        {"type": "confirmed", "text": "<strong>The Olaniyan Family</strong> — Year 4 admission accepted. Deposit ₦1.2M received via Paystack.", "time": "1 hour ago"},
        {"type": "replied",   "text": "<strong>Mrs Bankole</strong> — Asked about transport routes from Ikoyi. ReachNG sent the bus schedule + termly fee.", "time": "2 hours ago"},
        {"type": "confirmed", "text": "<strong>Mr Adebowale</strong> — Sixth Form scholarship application received. Forwarded to Head of Sixth Form.", "time": "3 hours ago"},
        {"type": "sent",      "text": "<strong>Mrs Eze</strong> — After-hours enquiry at 9:15pm. ReachNG replied with prospectus in 90 seconds.", "time": "5 hours ago"},
        {"type": "confirmed", "text": "<strong>Diaspora family (Atlanta)</strong> — Video tour booked for Saturday. Two children, Year 5 + Year 8.", "time": "6 hours ago"},
        {"type": "replied",   "text": "<strong>Mr Ojo</strong> — Scholarship enquiry. ReachNG qualified and routed to Admissions Director.", "time": "1 hour ago"},
    ],
    "pipeline_label": "Admissions Pipeline",
    "pipeline_columns": ["Family", "Year Group", "Fee Pipeline", "Status", "Last Touch"],
    "pipeline": [
        {"col1": "The Olaniyan Family", "col2": "Year 4",        "col3": "₦7.2M / term",  "status": "confirmed", "col5": "1 hour ago"},
        {"col1": "Mr Adebowale",        "col2": "Sixth Form",    "col3": "₦9.8M / term",  "status": "confirmed", "col5": "3 hours ago"},
        {"col1": "Diaspora family",     "col2": "Year 5 + 8",    "col3": "₦16M / term",   "status": "confirmed", "col5": "6 hours ago"},
        {"col1": "Mrs Adeleke",         "col2": "Year 7",        "col3": "₦8.4M / term",  "status": "pending",   "col5": "15 mins ago"},
        {"col1": "Dr & Mrs Okonkwo",    "col2": "Year 5 + 10",   "col3": "₦17.4M / term", "status": "pending",   "col5": "42 mins ago"},
        {"col1": "Mr Ojo",              "col2": "Year 10 (sch.)","col3": "Scholarship",   "status": "replied",   "col5": "1 hour ago"},
        {"col1": "Mrs Bankole",         "col2": "Year 2",        "col3": "₦6.4M / term",  "status": "replied",   "col5": "2 hours ago"},
        {"col1": "Mrs Eze",             "col2": "Pre-K",         "col3": "₦4.2M / term",  "status": "new",       "col5": "5 hours ago"},
    ],
    "holding_message": "Hi! Thanks for reaching out to Lagoon British International School. Our Admissions team will be right back with the prospectus, fee schedule and tour availability. If urgent, please mention your child's year group so we can prepare relevant materials.",
}


PROFESSIONAL_SERVICES = {
    "brand": "Adesina & Co. Solicitors",
    "tagline": "Commercial Law · Property · Corporate Advisory · Lagos",
    "category": "Legal",
    "intro_label": "Client Enquiry & Matter Inbox",
    "stats": [
        {"label": "New Enquiries (Week)", "value_num": 22, "value_prefix": "", "value_suffix": "", "change": "Qualified leads", "tone": "orange"},
        {"label": "Consultations Booked", "value_num": 9,  "value_prefix": "", "value_suffix": "", "change": "Paid first sessions", "tone": "green"},
        {"label": "Matters Opened",       "value_num": 14, "value_prefix": "₦", "value_suffix": "M", "change": "in retainer pipeline", "tone": "gold"},
        {"label": "Avg. Response Time",   "value_num": 6,  "value_prefix": "", "value_suffix": " min", "change": "Was 24+ hours", "tone": "blue"},
    ],
    "hitl_section_label": "Pending Approval",
    "hitl_drafts": [
        {"name": "Mrs Folorunsho", "initials": "FF", "time": "20 minutes ago", "tag": "property", "tag_label": "Property Dispute",
         "inbound": "Good evening. My family is in a land dispute in Lekki Phase 1 — there are competing C of O claims. Can you take a look at the documents and advise?",
         "draft": "Good evening Mrs Folorunsho, thank you for reaching out. Land disputes around Lekki Phase 1 with competing C of O claims are sensitive but workable — we handle several each year. Initial step is a 60-minute documents review (₦150,000) where we cross-reference both C of Os against the Lagos State Land Bureau records, identify which is original vs derivative, and outline a litigation or negotiation path. Could you send the C of Os, deeds and any correspondence by email? I'll have our property partner reserve a slot this week."},
        {"name": "Mr Eboigbe", "initials": "BE", "time": "1 hour ago", "tag": "corporate", "tag_label": "Company Setup",
         "inbound": "Setting up a fintech in Nigeria. Need to understand CBN sandbox vs full PSB licence path, and incorporation. Do you handle that?",
         "draft": "Hi Mr Eboigbe, yes — we set up several fintechs each year and our partners advise on CBN regulatory routing. Quick framing:\n\n• Sandbox = good for product validation, lower capital floor, time-limited (6–18 months) → suitable if you're still iterating.\n• Full PSB licence = ₦5B minimum capital, multi-stage CBN approval, 9–18 months — only sensible if you're past PMF and have institutional capital.\n\nIncorporation (CAC + fintech-specific articles) usually runs alongside the licence application.\n\nFirst step: 90-minute regulatory strategy call (₦300,000), output is a written routing memo with timelines and capital plan. Available Thursday 2pm or Friday 10am — which works?"},
        {"name": "Tola Ogunsanya", "initials": "TO", "time": "2 hours ago", "tag": "employment", "tag_label": "Employment Dispute",
         "inbound": "Just been let go from a senior banking role. They're trying to enforce a 12-month non-compete. Is that even legal in Nigeria?",
         "draft": "Hi Tola, sorry to hear about the role. Short answer: 12 months is on the very long end and Nigerian courts (per Koumoulis v Leventis Motors and subsequent cases) only enforce non-competes that are reasonable in scope, geography AND duration. 6 months is the typical ceiling courts will uphold for senior roles; 12 months is challengeable and often reduced or struck out.\n\nWe'd need to see the contract clause + your termination letter to give a firm view. Initial review is ₦100,000 for a 1-page written opinion, or ₦400,000 if you want us to draft a response letter and negotiate. Confidentiality assured. Can you send the docs through?"},
    ],
    "secondary_section": {
        "title": "Active Matter Workload",
        "type": "matters_list",
        "data": [
            {"matter": "OAU v. Sterling Bank — fixed deposit dispute",          "stage": "Discovery",  "next": "Witness statements due Fri", "status": "confirmed"},
            {"matter": "Lekki Phase 1 land — Adekoya estate",                   "stage": "Pleadings",  "next": "Statement of claim — Mon",   "status": "confirmed"},
            {"matter": "FlexFinance Ltd — CBN PSB application",                 "stage": "Submission", "next": "CBN response window — 10 days", "status": "tentative"},
            {"matter": "Heritage v. Ofili — employment termination",            "stage": "Mediation",  "next": "Session Wed 2pm",            "status": "confirmed"},
            {"matter": "Greenfield Estates — joint venture documentation",      "stage": "Drafting",   "next": "Heads of terms by Thursday", "status": "confirmed"},
        ],
    },
    "activity_label": "Recent Activity",
    "activity": [
        {"type": "confirmed", "text": "<strong>FlexFinance Ltd</strong> — Engagement letter signed. Retainer ₦8M for fintech setup. First call scheduled.", "time": "2 hours ago"},
        {"type": "replied",   "text": "<strong>Heritage Investments</strong> — Asked for an update on the mediation. Senior associate sent the brief.", "time": "3 hours ago"},
        {"type": "confirmed", "text": "<strong>Mrs Adekoya</strong> — Property review fee paid (₦150,000). Documents lodged with property partner.", "time": "4 hours ago"},
        {"type": "sent",      "text": "<strong>Mr Bello</strong> — Enquiry received Saturday 10pm. ReachNG replied with engagement framework in 4 minutes.", "time": "1 day ago"},
        {"type": "confirmed", "text": "<strong>Greenfield Estates</strong> — JV term sheet draft 1 sent. Client review scheduled for Thursday.", "time": "5 hours ago"},
        {"type": "replied",   "text": "<strong>Tola Ogunsanya</strong> — Employment enquiry. ReachNG advised on non-compete enforceability and quoted scope.", "time": "2 hours ago"},
    ],
    "pipeline_label": "Client Pipeline",
    "pipeline_columns": ["Client", "Matter Type", "Engagement Value", "Status", "Last Touch"],
    "pipeline": [
        {"col1": "FlexFinance Ltd",   "col2": "CBN PSB Setup",     "col3": "₦8M retainer",   "status": "confirmed", "col5": "2 hours ago"},
        {"col1": "Greenfield Estates","col2": "JV Documentation",  "col3": "₦4.5M",          "status": "confirmed", "col5": "5 hours ago"},
        {"col1": "Mrs Adekoya",       "col2": "Property Dispute",  "col3": "₦150K (review)", "status": "confirmed", "col5": "4 hours ago"},
        {"col1": "Mrs Folorunsho",    "col2": "Land Dispute",      "col3": "₦150K (review)", "status": "pending",   "col5": "20 mins ago"},
        {"col1": "Mr Eboigbe",        "col2": "Fintech Setup",     "col3": "₦300K (call)",   "status": "pending",   "col5": "1 hour ago"},
        {"col1": "Tola Ogunsanya",    "col2": "Employment Dispute","col3": "₦100K–₦400K",   "status": "replied",   "col5": "2 hours ago"},
        {"col1": "Heritage Inv.",     "col2": "Mediation",         "col3": "Ongoing matter", "status": "replied",   "col5": "3 hours ago"},
        {"col1": "Mr Bello",          "col2": "Contract Review",   "col3": "TBC",            "status": "new",       "col5": "1 day ago"},
    ],
    "holding_message": "Thank you for reaching out to Adesina & Co. A senior associate will respond within minutes with next steps. For urgent matters, please indicate the practice area (commercial / property / corporate / dispute). All enquiries are treated with strict confidentiality.",
}


SMALL_BUSINESS = {
    "brand": "Glow Studio Lagos",
    "tagline": "Beauty · Spa · Hair · Lekki & VI",
    "category": "Small Business",
    "intro_label": "Bookings & Customer Inbox",
    "stats": [
        {"label": "DMs This Week",        "value_num": 142, "value_prefix": "", "value_suffix": "", "change": "WhatsApp + Instagram", "tone": "orange"},
        {"label": "Bookings Confirmed",   "value_num": 58,  "value_prefix": "", "value_suffix": "", "change": "Deposits received", "tone": "green"},
        {"label": "Revenue Tracked",      "value_num": 3.6, "value_prefix": "₦", "value_suffix": "M", "change": "from confirmed bookings", "tone": "gold"},
        {"label": "No-Show Rate",         "value_num": 4,   "value_prefix": "", "value_suffix": "%",  "change": "Was 18% before deposits", "tone": "blue"},
    ],
    "hitl_section_label": "Pending Approval",
    "hitl_drafts": [
        {"name": "Tomi Falade", "initials": "TF", "time": "5 minutes ago", "tag": "booking", "tag_label": "Hair Booking",
         "inbound": "Hi! Saw your IG. Looking to book a knotless braids appointment for Friday. Do you have anything between 10am and 2pm? How much?",
         "draft": "Hi Tomi! 👋 Thanks for reaching out — we love your style. For Friday between 10am–2pm we have an 11am slot with Aunty Lola (our senior braider). Knotless braids start at ₦35,000 (medium length, hip length is ₦45,000). Booking is confirmed once a ₦10,000 deposit is paid (refundable if cancelled 24h before). I'll send the Paystack link now — shall I lock in 11am Friday for you?"},
        {"name": "Chiamaka Ude", "initials": "CU", "time": "18 minutes ago", "tag": "spa", "tag_label": "Spa Day Package",
         "inbound": "I want to book a spa day for me and 3 friends — bridal squad thing. Saturday afternoon. What packages do you have for groups?",
         "draft": "Hi Chiamaka! Congrats on the wedding 🎉 Our Bridal Squad Package is built for exactly this. ₦80,000 per person includes:\n\n• Welcome cocktails + small chops\n• Full-body massage (60 mins)\n• Express facial\n• Mani + pedi\n• Hair styling\n\nFor a group of 4 on Saturday afternoon I can hold our private suite from 1pm–5pm. Group deposit is ₦80,000 (refundable up to 48h before). Want me to lock that in? I'll send the Paystack link and a planning checklist."},
        {"name": "Bisi Akande", "initials": "BA", "time": "47 minutes ago", "tag": "loyalty", "tag_label": "Returning Client",
         "inbound": "Hey! It's Bisi. Want to do my usual — gel mani, brow wax, lash fill. Anything tomorrow?",
         "draft": "Hi Bisi! Always lovely to hear from you 💕 For tomorrow I have 2pm or 4:30pm with Naomi — she's done your lashes the last 3 times. Gel mani + brow wax + lash fill is ₦28,000 (loyalty pricing). No deposit needed since you're a regular — I'll just hold the slot. Which time?"},
    ],
    "secondary_section": {
        "title": "Today's Schedule",
        "type": "schedule_list",
        "data": [
            {"time": "10:00am", "service": "Bridal hair trial",            "client": "Funmi A.",       "status": "confirmed"},
            {"time": "11:30am", "service": "Knotless braids (medium)",     "client": "Yetunde O.",     "status": "confirmed"},
            {"time": "1:00pm",  "service": "Full-body massage",            "client": "Mrs Bankole",    "status": "confirmed"},
            {"time": "3:00pm",  "service": "Lash extensions (full set)",   "client": "Adaora N.",      "status": "tentative"},
            {"time": "4:30pm",  "service": "Bridal Squad — 4 pax",         "client": "Chiamaka U.",    "status": "tentative"},
            {"time": "6:00pm",  "service": "Gel mani + lash fill",         "client": "Bisi A.",        "status": "tentative"},
        ],
    },
    "activity_label": "Recent Activity",
    "activity": [
        {"type": "confirmed", "text": "<strong>Funmi Adesanya</strong> — Bridal hair trial booked. ₦25,000 deposit received via Paystack.", "time": "20 mins ago"},
        {"type": "replied",   "text": "<strong>Doyin O.</strong> — Asked for ombré lash quote. ReachNG sent the price card.", "time": "1 hour ago"},
        {"type": "confirmed", "text": "<strong>Yetunde Ogunyemi</strong> — Knotless braids tomorrow 11:30am. Deposit ₦15,000 paid.", "time": "2 hours ago"},
        {"type": "sent",      "text": "<strong>New IG follower</strong> — Asked for studio location at 10:47pm. ReachNG sent address + parking info in 60s.", "time": "5 hours ago"},
        {"type": "confirmed", "text": "<strong>Adaora N.</strong> — Lash extension booking. Reschedule from Friday → Wednesday confirmed.", "time": "3 hours ago"},
        {"type": "replied",   "text": "<strong>Mrs Adekunle</strong> — VIP gift card enquiry. ReachNG explained denominations + delivery options.", "time": "4 hours ago"},
    ],
    "pipeline_label": "Booking Pipeline",
    "pipeline_columns": ["Client", "Service", "Slot", "Status", "Last Touch"],
    "pipeline": [
        {"col1": "Funmi Adesanya",   "col2": "Bridal hair trial",          "col3": "Today 10am · ₦35K",   "status": "confirmed", "col5": "20 mins ago"},
        {"col1": "Yetunde Ogunyemi", "col2": "Knotless braids",            "col3": "Tomorrow 11:30 · ₦35K","status": "confirmed", "col5": "2 hours ago"},
        {"col1": "Mrs Bankole",      "col2": "Full-body massage",          "col3": "Today 1pm · ₦25K",     "status": "confirmed", "col5": "5 hours ago"},
        {"col1": "Tomi Falade",      "col2": "Knotless braids",            "col3": "Fri 11am",             "status": "pending",   "col5": "5 mins ago"},
        {"col1": "Chiamaka Ude",     "col2": "Bridal Squad (4 pax)",       "col3": "Sat 1pm–5pm · ₦320K",  "status": "pending",   "col5": "18 mins ago"},
        {"col1": "Bisi Akande",      "col2": "Mani + brow + lash fill",    "col3": "Tomorrow · ₦28K",      "status": "replied",   "col5": "47 mins ago"},
        {"col1": "Doyin O.",         "col2": "Ombré lash quote",           "col3": "TBC",                  "status": "replied",   "col5": "1 hour ago"},
        {"col1": "Adaora N.",        "col2": "Lash extensions",            "col3": "Wed 3pm · ₦40K",       "status": "new",       "col5": "3 hours ago"},
    ],
    "holding_message": "Hi babe! 💕 Thanks for reaching out to Glow Studio. We'll be right back with availability and pricing — usually within 5 mins! For bookings, please share: service you want, day/time, and whether it's a regular or first-visit. Xx",
}


DATASETS: dict[str, dict] = {
    "hospitality":           HOSPITALITY,
    "real_estate":           REAL_ESTATE,
    "education":             EDUCATION,
    "professional_services": PROFESSIONAL_SERVICES,
    "small_business":        SMALL_BUSINESS,

    # Friendly aliases for sales links
    "mercury":  HOSPITALITY,
    "estate":   REAL_ESTATE,
    "school":   EDUCATION,
    "legal":    PROFESSIONAL_SERVICES,
    "smb":      SMALL_BUSINESS,
    "sme":      SMALL_BUSINESS,
}


def get_dataset(vertical: Optional[str] = None) -> dict:
    """Return demo dataset for a vertical, defaulting to hospitality (Mercury)."""
    if not vertical:
        return HOSPITALITY
    return DATASETS.get(vertical.lower(), HOSPITALITY)


def list_verticals() -> list[str]:
    """Canonical vertical keys (no aliases)."""
    return ["hospitality", "real_estate", "education", "professional_services", "small_business"]
