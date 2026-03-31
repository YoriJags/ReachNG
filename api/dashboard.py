"""
Live pipeline dashboard — single HTML page, auto-refreshes every 30 seconds.
Served at GET /dashboard
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>ReachNG — Pipeline</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0d0d0d;
    color: #e8e8e8;
    min-height: 100vh;
    padding: 32px 24px;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 40px;
  }

  .logo { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
  .logo span { color: #ff5c00; }

  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #00c851; display: inline-block;
    margin-right: 6px; animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
  }

  .live-badge {
    font-size: 12px; color: #888; display: flex; align-items: center;
  }

  /* ── Summary bar ── */
  .summary-bar {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }

  .stat-card {
    background: #161616;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 20px 24px;
  }

  .stat-card .label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; }
  .stat-card .value { font-size: 32px; font-weight: 700; }
  .stat-card.fire .value  { color: #ff5c00; }
  .stat-card.green .value { color: #00c851; }
  .stat-card.amber .value { color: #ffbb33; }
  .stat-card.blue .value  { color: #4da6ff; }

  /* ── Verticals ── */
  .section-title {
    font-size: 13px; color: #555; text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 16px;
  }

  .verticals {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }

  .vertical-card {
    background: #161616;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 24px;
  }

  .vertical-card h3 {
    font-size: 15px; font-weight: 600; margin-bottom: 20px;
    display: flex; align-items: center; gap: 8px;
  }

  .v-row {
    display: flex; justify-content: space-between;
    align-items: center; padding: 8px 0;
    border-bottom: 1px solid #1a1a1a; font-size: 14px;
  }
  .v-row:last-child { border-bottom: none; }
  .v-row .lbl { color: #666; }
  .v-row .val { font-weight: 600; }
  .val.replied   { color: #ffbb33; }
  .val.converted { color: #00c851; }
  .val.contacted { color: #4da6ff; }

  /* ── Progress bar ── */
  .limit-bar-wrap { margin-bottom: 40px; }
  .limit-bar-track {
    background: #1a1a1a; border-radius: 6px; height: 8px; overflow: hidden;
  }
  .limit-bar-fill {
    height: 100%; border-radius: 6px;
    background: linear-gradient(90deg, #ff5c00, #ff8c00);
    transition: width 0.6s ease;
  }
  .limit-label {
    display: flex; justify-content: space-between;
    font-size: 12px; color: #555; margin-bottom: 8px;
  }

  /* ── Recent replies ── */
  .replies-list { display: flex; flex-direction: column; gap: 12px; }

  .reply-card {
    background: #161616;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 18px 20px;
  }

  .reply-header {
    display: flex; justify-content: space-between;
    align-items: center; margin-bottom: 10px;
  }

  .reply-name { font-weight: 600; font-size: 15px; }

  .intent-badge {
    font-size: 11px; font-weight: 600; padding: 3px 10px;
    border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .intent-interested  { background: #1a3d1a; color: #00c851; }
  .intent-not_now     { background: #2e2b1a; color: #ffbb33; }
  .intent-opted_out   { background: #3d1a1a; color: #ff4444; }
  .intent-referral    { background: #1a2e3d; color: #4da6ff; }
  .intent-question    { background: #2a1a3d; color: #c084fc; }
  .intent-unknown     { background: #1e1e1e; color: #555; }

  .reply-meta { font-size: 12px; color: #555; margin-bottom: 8px; }
  .reply-summary { font-size: 13px; color: #aaa; line-height: 1.5; }

  /* ── ROI banner ── */
  .roi-banner {
    background: linear-gradient(135deg, #1a1a0d 0%, #161616 100%);
    border: 1px solid #333;
    border-left: 3px solid #ff5c00;
    border-radius: 12px;
    padding: 24px 28px;
    margin-bottom: 40px;
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: center;
    justify-content: space-between;
  }
  .roi-label-text { font-size: 20px; font-weight: 700; color: #ff5c00; }
  .roi-sub { font-size: 12px; color: #555; margin-top: 4px; }
  .roi-stats { display: flex; gap: 32px; flex-wrap: wrap; }
  .roi-stat .r-val { font-size: 22px; font-weight: 700; }
  .roi-stat .r-lbl { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.6px; margin-top: 2px; }
  .roi-stat.green .r-val { color: #00c851; }
  .roi-stat.amber .r-val { color: #ffbb33; }
  .roi-stat.blue  .r-val { color: #4da6ff; }

  /* ── Approvals queue ── */
  .approvals-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 40px; }

  .approval-card {
    background: #161616;
    border: 1px solid #2a2a1a;
    border-radius: 12px;
    padding: 18px 20px;
  }

  .approval-header {
    display: flex; justify-content: space-between;
    align-items: center; margin-bottom: 10px;
  }

  .approval-name { font-weight: 600; font-size: 15px; }
  .approval-meta { font-size: 12px; color: #555; margin-bottom: 10px; }
  .approval-message {
    font-size: 13px; color: #ccc; line-height: 1.6;
    background: #0d0d0d; border-radius: 8px; padding: 12px 14px;
    margin-bottom: 12px; white-space: pre-wrap;
  }

  .approval-actions { display: flex; gap: 8px; flex-wrap: wrap; }

  .btn {
    border: none; border-radius: 8px; padding: 7px 16px;
    font-size: 12px; font-weight: 600; cursor: pointer;
    letter-spacing: 0.3px; transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.8; }
  .btn-approve { background: #00c851; color: #000; }
  .btn-skip    { background: #2a2a2a; color: #888; }
  .btn-edit    { background: #1a2a3d; color: #4da6ff; }

  .channel-badge {
    font-size: 10px; font-weight: 600; padding: 2px 8px;
    border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .channel-whatsapp { background: #1a3d1a; color: #00c851; }
  .channel-email    { background: #1a2a3d; color: #4da6ff; }

  .post-context {
    font-size: 12px; color: #666; font-style: italic;
    background: #111; border-left: 2px solid #333;
    padding: 8px 12px; border-radius: 0 6px 6px 0;
    margin-bottom: 10px; line-height: 1.5;
  }

  .source-badge {
    font-size: 10px; font-weight: 600; padding: 2px 7px;
    border-radius: 20px; margin-left: 6px;
  }
  .source-maps     { background: #1a1a2e; color: #4da6ff; }
  .source-social   { background: #1a0d2e; color: #c084fc; }
  .platform-instagram { color: #e1306c; }
  .platform-twitter   { color: #1da1f2; }
  .platform-facebook  { color: #4267B2; }

  /* ── Social signals ── */
  .signals-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-bottom: 40px;
  }
  .signal-stat {
    background: #161616; border: 1px solid #222; border-radius: 10px;
    padding: 16px 20px;
  }
  .signal-stat .s-val { font-size: 28px; font-weight: 700; color: #c084fc; }
  .signal-stat .s-lbl { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.6px; margin-top: 4px; }

  .approvals-empty { color: #333; font-size: 14px; text-align: center; padding: 32px; }
  .approve-all-bar {
    display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap;
  }
  .approve-count { font-size: 14px; color: #888; }

  /* ── Hook generator ── */
  .hook-form {
    background: #161616; border: 1px solid #222; border-radius: 12px;
    padding: 24px; margin-bottom: 16px;
  }
  .hook-form .row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
  .hook-form input, .hook-form select {
    background: #0d0d0d; border: 1px solid #2a2a2a; border-radius: 8px;
    color: #e8e8e8; font-size: 14px; padding: 9px 14px;
    font-family: inherit; flex: 1; min-width: 160px;
  }
  .hook-form input:focus, .hook-form select:focus { outline: none; border-color: #ff5c00; }

  .hooks-output { display: flex; flex-direction: column; gap: 10px; margin-bottom: 40px; }
  .hook-card {
    background: #161616; border: 1px solid #222; border-radius: 10px;
    padding: 16px 20px;
  }
  .hook-text { font-size: 16px; font-weight: 600; color: #e8e8e8; margin-bottom: 6px; }
  .hook-meta { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .hook-format { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.6px; }
  .hook-why { font-size: 12px; color: #888; flex: 1; }
  .hook-copy {
    font-size: 11px; background: #222; color: #aaa; border: none;
    border-radius: 6px; padding: 4px 10px; cursor: pointer;
  }
  .hook-copy:hover { background: #333; }

  .trending-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 40px; }
  .trending-pill {
    background: #1a1a2e; color: #888; font-size: 12px;
    padding: 5px 12px; border-radius: 20px; max-width: 340px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  /* ── Edit modal ── */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.85); z-index: 999;
    align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal-box {
    background: #161616; border: 1px solid #333; border-radius: 16px;
    padding: 28px; width: 90%; max-width: 560px;
  }
  .modal-box h3 { font-size: 16px; margin-bottom: 16px; }
  .modal-box textarea {
    width: 100%; background: #0d0d0d; border: 1px solid #333;
    border-radius: 8px; color: #e8e8e8; font-size: 14px; line-height: 1.6;
    padding: 12px; resize: vertical; min-height: 140px;
    font-family: inherit;
  }
  .modal-actions { display: flex; gap: 10px; margin-top: 14px; justify-content: flex-end; }

  .empty { color: #333; font-size: 14px; text-align: center; padding: 40px; }

  #last-updated { font-size: 11px; color: #333; text-align: right; margin-top: 48px; }
</style>
</head>
<body>

<header>
  <div class="logo">Reach<span>NG</span></div>
  <div class="live-badge"><span class="status-dot"></span> Live — refreshes every 30s</div>
</header>

<!-- ROI Banner -->
<div class="roi-banner" id="roi-banner">
  <div>
    <div class="roi-label-text" id="roi-label">Loading ROI…</div>
    <div class="roi-sub">Last 30 days — AI vs manual outreach cost</div>
  </div>
  <div class="roi-stats">
    <div class="roi-stat green"><div class="r-val" id="roi-value">—</div><div class="r-lbl">Value Generated</div></div>
    <div class="roi-stat amber"><div class="r-val" id="roi-api-cost">—</div><div class="r-lbl">AI Cost</div></div>
    <div class="roi-stat blue"><div class="r-val" id="roi-msgs">—</div><div class="r-lbl">Messages Sent</div></div>
  </div>
</div>

<!-- Summary bar -->
<div class="summary-bar" id="summary-bar">
  <div class="stat-card fire"><div class="label">Total Contacted</div><div class="value" id="s-contacted">—</div></div>
  <div class="stat-card amber"><div class="label">Replied</div><div class="value" id="s-replied">—</div></div>
  <div class="stat-card green"><div class="label">Converted</div><div class="value" id="s-converted">—</div></div>
  <div class="stat-card blue"><div class="label">Sent Today</div><div class="value" id="s-today">—</div></div>
</div>

<!-- Daily limit bar -->
<div class="limit-bar-wrap">
  <div class="limit-label">
    <span>Daily send limit</span>
    <span id="limit-label-right">— / —</span>
  </div>
  <div class="limit-bar-track">
    <div class="limit-bar-fill" id="limit-bar" style="width:0%"></div>
  </div>
</div>

<!-- Verticals -->
<p class="section-title">Pipeline by Vertical</p>
<div class="verticals" id="verticals-grid">
  <div class="vertical-card"><div class="empty">Loading…</div></div>
</div>

<!-- Social Signals -->
<p class="section-title">Social Signals <span style="color:#c084fc;font-size:11px;margin-left:6px;">Instagram · Twitter · Facebook</span></p>
<div class="signals-grid" id="signals-grid">
  <div class="signal-stat"><div class="s-val" id="sig-total">—</div><div class="s-lbl">Found This Week</div></div>
  <div class="signal-stat"><div class="s-val" id="sig-ig" style="color:#e1306c;">—</div><div class="s-lbl">Instagram</div></div>
  <div class="signal-stat"><div class="s-val" id="sig-tw" style="color:#1da1f2;">—</div><div class="s-lbl">Twitter / X</div></div>
  <div class="signal-stat"><div class="s-val" id="sig-fb" style="color:#4267B2;">—</div><div class="s-lbl">Facebook</div></div>
</div>

<!-- Pending Approvals -->
<p class="section-title">Pending Approvals <span id="approval-count-badge" style="color:#ff5c00;margin-left:8px;"></span></p>
<div class="approve-all-bar" id="approve-all-bar" style="display:none;">
  <button class="btn btn-approve" onclick="approveAll()">✓ Approve All</button>
  <button class="btn btn-skip" onclick="skipAll()">✕ Skip All</button>
  <span class="approve-count" id="approve-all-label"></span>
</div>
<div class="approvals-list" id="approvals-list">
  <div class="approvals-empty">Loading…</div>
</div>

<!-- Recent replies -->
<p class="section-title">Recent Replies</p>
<div class="replies-list" id="replies-list">
  <div class="empty">Loading…</div>
</div>

<!-- Run Campaign -->
<p class="section-title">Run Campaign <span style="color:#ff5c00;font-size:11px;margin-left:6px;">Trigger Outreach</span></p>
<div class="hook-form" id="run-campaign-form">
  <div class="row">
    <select id="rc-vertical">
      <option value="real_estate">🏠 Real Estate</option>
      <option value="recruitment">👥 Recruitment</option>
      <option value="events">🎉 Events</option>
      <option value="fintech">💳 Fintech</option>
      <option value="legal">⚖️ Legal</option>
      <option value="logistics">🚚 Logistics</option>
    </select>
    <input id="rc-max" type="number" value="10" min="1" max="60" style="max-width:90px;" title="Max contacts" />
    <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#aaa;white-space:nowrap;">
      <input type="checkbox" id="rc-dryrun" checked style="width:auto;accent-color:#ff5c00;" /> Dry run
    </label>
    <button class="btn btn-approve" id="rc-btn" onclick="runCampaign()" style="white-space:nowrap;">▶ Run</button>
  </div>
  <div id="rc-result" style="margin-top:12px;display:none;"></div>
</div>

<!-- Client Onboarding -->
<p class="section-title">Client Onboarding <span style="color:#ff5c00;font-size:11px;margin-left:6px;">3-Step Setup</span></p>
<div class="hook-form">

  <!-- Step 1: Brief -->
  <p style="font-size:11px;color:#ff5c00;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Step 1 — Create Client Brief</p>
  <div class="row">
    <input id="ob-name" placeholder="Client name e.g. Mercury Lagos" style="flex:1;" />
    <select id="ob-vertical">
      <option value="real_estate">🏠 Real Estate</option>
      <option value="recruitment">👥 Recruitment</option>
      <option value="events">🎉 Events</option>
      <option value="fintech">💳 Fintech</option>
      <option value="legal">⚖️ Legal</option>
      <option value="logistics">🚚 Logistics</option>
    </select>
    <select id="ob-channel">
      <option value="whatsapp">WhatsApp</option>
      <option value="email">Email</option>
    </select>
  </div>
  <div class="row" style="margin-top:8px;">
    <select id="ob-plan" style="flex:1;">
      <option value="">— Select Plan —</option>
      <option value="starter">Starter — ₦50,000 setup + ₦50,000/mo · 300 msgs · 1 vertical · WhatsApp</option>
      <option value="growth">Growth — ₦120,000 setup + ₦120,000/mo · 1,000 msgs · 3 verticals · WhatsApp + Email</option>
      <option value="agency">Agency — ₦250,000 setup + ₦250,000/mo · Unlimited · All verticals · ROI reporting</option>
    </select>
    <input id="ob-city" placeholder="City (default: Lagos) e.g. London, UK" style="flex:1;" title="Campaigns will search this city" />
  </div>
  <div class="row" style="margin-top:8px;">
    <input id="ob-wa-account" placeholder="Unipile WhatsApp Account ID (client's own number)" style="flex:1;" />
    <input id="ob-email-account" placeholder="Unipile Email Account ID (optional)" style="flex:1;" />
  </div>
  <p style="font-size:11px;color:#555;margin-top:4px;margin-bottom:8px;">Account IDs found in Unipile dashboard after client scans QR code. Leave blank to use your default number.</p>
  <textarea id="ob-brief" rows="4" placeholder="Who is this client? What do they sell? What tone should messages take? Who is their target customer?&#10;&#10;Example: Mercury Lagos is a luxury property agency on Victoria Island. We sell high-end apartments ₦50M+. Tone: professional, warm. Target: developers, HNI buyers, diaspora investors." style="width:100%;background:#111;border:1px solid #2a2a2a;border-radius:8px;padding:12px;color:#e8e8e8;font-size:13px;resize:vertical;margin-top:8px;font-family:inherit;"></textarea>
  <button class="btn btn-approve" id="ob-create-btn" onclick="createClient()" style="margin-top:10px;white-space:nowrap;">✓ Save Client</button>
  <div id="ob-create-result" style="margin-top:10px;display:none;"></div>

  <div style="border-top:1px solid #1e1e1e;margin:20px 0;"></div>

  <!-- Step 2: Portal -->
  <p style="font-size:11px;color:#ff5c00;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Step 2 — Generate Portal Link</p>
  <div class="row">
    <input id="ob-portal-name" placeholder="Client name (same as above)" style="flex:1;" />
    <button class="btn btn-approve" id="ob-portal-btn" onclick="generatePortal()" style="white-space:nowrap;">🔗 Generate Portal</button>
  </div>
  <div id="ob-portal-result" style="margin-top:10px;display:none;"></div>

  <div style="border-top:1px solid #1e1e1e;margin:20px 0;"></div>

  <!-- Step 3: Run Campaign -->
  <p style="font-size:11px;color:#ff5c00;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Step 3 — Run First Campaign</p>
  <div class="row">
    <input id="ob-run-name" placeholder="Client name" style="flex:1;" />
    <select id="ob-run-vertical">
      <option value="real_estate">🏠 Real Estate</option>
      <option value="recruitment">👥 Recruitment</option>
      <option value="events">🎉 Events</option>
      <option value="fintech">💳 Fintech</option>
      <option value="legal">⚖️ Legal</option>
      <option value="logistics">🚚 Logistics</option>
    </select>
    <input id="ob-run-max" type="number" value="30" min="1" max="60" style="max-width:80px;" title="Max contacts" />
    <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#aaa;white-space:nowrap;">
      <input type="checkbox" id="ob-run-dryrun" checked style="width:auto;accent-color:#ff5c00;" /> Dry run
    </label>
    <button class="btn btn-approve" id="ob-run-btn" onclick="runClientCampaign()" style="white-space:nowrap;">▶ Run</button>
  </div>
  <div id="ob-run-result" style="margin-top:10px;display:none;"></div>
</div>

<!-- Export Contacts -->
<p class="section-title">Export Contacts <span style="color:#ff5c00;font-size:11px;margin-left:6px;">Google Sheets / CSV</span></p>
<div class="hook-form">
  <div class="row">
    <select id="exp-vertical">
      <option value="">All Verticals</option>
      <option value="real_estate">🏠 Real Estate</option>
      <option value="recruitment">👥 Recruitment</option>
      <option value="events">🎉 Events</option>
      <option value="fintech">💳 Fintech</option>
      <option value="legal">⚖️ Legal</option>
      <option value="logistics">🚚 Logistics</option>
    </select>
    <select id="exp-status">
      <option value="">All Statuses</option>
      <option value="new">New</option>
      <option value="contacted">Contacted</option>
      <option value="replied">Replied</option>
      <option value="converted">Converted</option>
      <option value="opted_out">Opted Out</option>
    </select>
    <button class="btn btn-approve" onclick="exportContacts()" style="white-space:nowrap;">⬇ Download CSV</button>
  </div>
  <p style="font-size:12px;color:#666;margin-top:8px;">Open the CSV in Google Sheets via File → Import. All contact fields included.</p>
</div>

<!-- Invoice Collection -->
<p class="section-title">Invoice Collection <span style="color:#f5c842;font-size:11px;margin-left:6px;">Agency Pro · AI Payment Reminders</span></p>
<div class="hook-form">
  <!-- Add Invoice -->
  <p style="font-size:11px;color:#ff5c00;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Add Invoice</p>
  <div class="row">
    <input id="inv-client" placeholder="Your client name" style="flex:1;" />
    <input id="inv-debtor" placeholder="Debtor name (who owes)" style="flex:1;" />
    <input id="inv-phone" placeholder="+2348012345678" style="flex:1;" />
  </div>
  <div class="row" style="margin-top:8px;">
    <input id="inv-amount" type="number" placeholder="Amount (₦)" style="flex:1;" min="1" />
    <input id="inv-due" type="date" style="flex:1;" />
    <input id="inv-desc" placeholder="Description e.g. Web design services" style="flex:2;" />
  </div>
  <div class="row" style="margin-top:8px;">
    <input id="inv-custom-days" placeholder="Custom reminder days (optional) e.g. 0,5,10,20" style="flex:1;" title="Comma-separated days after due date" />
    <select id="inv-custom-tones" multiple style="flex:1;height:36px;background:#111;border:1px solid #2a2a2a;border-radius:8px;padding:4px 8px;color:#e8e8e8;font-size:13px;" title="Hold Ctrl to select multiple tones in order">
      <option value="polite">Polite</option>
      <option value="firm">Firm</option>
      <option value="payment_plan">Payment Plan</option>
      <option value="final">Final Notice</option>
    </select>
    <button class="btn btn-approve" id="inv-add-btn" onclick="addInvoice()" style="white-space:nowrap;">+ Add Invoice</button>
  </div>
  <div id="inv-add-result" style="margin-top:8px;display:none;"></div>

  <div style="border-top:1px solid #1e1e1e;margin:20px 0;"></div>

  <!-- Invoice Stats -->
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <p style="font-size:11px;color:#ff5c00;text-transform:uppercase;letter-spacing:0.1em;">Outstanding Invoices</p>
    <div style="display:flex;gap:8px;">
      <input id="inv-filter-client" placeholder="Filter by client" style="max-width:160px;font-size:12px;padding:4px 8px;" />
      <button class="btn" onclick="loadInvoices()" style="background:#1a1a1a;border:1px solid #333;font-size:12px;padding:4px 12px;">Refresh</button>
    </div>
  </div>
  <div id="inv-stats" style="display:flex;gap:24px;margin-bottom:16px;"></div>
  <div id="inv-list"></div>
</div>

<!-- Hook Generator -->
<p class="section-title">Hook Generator <span style="color:#ff5c00;font-size:11px;margin-left:6px;">Content Intelligence</span></p>
<div class="hook-form">
  <div class="row">
    <select id="hk-vertical">
      <option value="real_estate">🏠 Real Estate</option>
      <option value="recruitment">👥 Recruitment</option>
      <option value="events">🎉 Events</option>
      <option value="fintech">💳 Fintech</option>
      <option value="legal">⚖️ Legal</option>
      <option value="logistics">🚚 Logistics</option>
    </select>
    <select id="hk-platform">
      <option value="instagram">📸 Instagram</option>
      <option value="twitter">🐦 Twitter / X</option>
      <option value="linkedin">💼 LinkedIn</option>
      <option value="whatsapp">📱 WhatsApp</option>
    </select>
    <input id="hk-count" type="number" value="8" min="3" max="15" style="max-width:80px;" />
  </div>
  <div class="row">
    <input id="hk-topic" placeholder="Topic — e.g. '3-bedroom apartments in Lekki Phase 1'" style="flex:2;" />
    <input id="hk-client" placeholder="Client name (optional)" />
  </div>
  <div class="row">
    <input id="hk-competitors" placeholder="Competitor handles (comma-separated, optional)" style="flex:2;" />
    <button class="btn btn-approve" id="hk-btn" onclick="generateHooks()" style="white-space:nowrap;">⚡ Generate Hooks</button>
  </div>
</div>
<div class="trending-pills" id="trending-pills" style="display:none;"></div>
<div class="hooks-output" id="hooks-output"></div>

<!-- Edit modal -->
<div class="modal-overlay" id="edit-modal">
  <div class="modal-box">
    <h3>Edit message before sending</h3>
    <textarea id="edit-textarea" placeholder="Type edited message…"></textarea>
    <div class="modal-actions">
      <button class="btn btn-skip" onclick="closeEdit()">Cancel</button>
      <button class="btn btn-approve" onclick="submitEdit()">✓ Save &amp; Send</button>
    </div>
  </div>
</div>

<div id="last-updated"></div>

<script>
const VERTICAL_ICONS = { real_estate: "🏠", recruitment: "👥", events: "🎉", fintech: "💳", legal: "⚖️", logistics: "🚚" };
const INTENT_LABELS  = { interested:"Interested", not_now:"Not Now", opted_out:"Opted Out", referral:"Referral", question:"Question", unknown:"Unknown" };

let editTargetId = null;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function fmt(n) { return n === undefined || n === null ? "0" : String(n); }

function fmtNgn(n) {
  if (!n && n !== 0) return "—";
  if (n >= 1_000_000) return "₦" + (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return "₦" + (n / 1_000).toFixed(0) + "k";
  return "₦" + n;
}

// ── Approval actions ──────────────────────────────────────────────────────────

async function approveOne(id) {
  await postJSON(`/api/v1/approvals/${id}/approve`);
  refresh();
}

async function skipOne(id) {
  await postJSON(`/api/v1/approvals/${id}/skip`);
  refresh();
}

function openEdit(id, currentMsg) {
  editTargetId = id;
  document.getElementById("edit-textarea").value = currentMsg;
  document.getElementById("edit-modal").classList.add("open");
}

function closeEdit() {
  editTargetId = null;
  document.getElementById("edit-modal").classList.remove("open");
}

async function submitEdit() {
  const msg = document.getElementById("edit-textarea").value.trim();
  if (!msg || !editTargetId) return;
  await postJSON(`/api/v1/approvals/${editTargetId}/edit`, { new_message: msg });
  closeEdit();
  refresh();
}

async function approveAll() {
  await postJSON("/api/v1/approvals/approve-all");
  refresh();
}

async function skipAll() {
  await postJSON("/api/v1/approvals/skip-all");
  refresh();
}

// ── Main refresh ──────────────────────────────────────────────────────────────

async function refresh() {
  try {
    const [pipeline, replies, approvals, roi, socialStats] = await Promise.all([
      fetchJSON("/api/v1/contacts/pipeline"),
      fetchJSON("/api/v1/contacts/replies?limit=10"),
      fetchJSON("/api/v1/approvals/"),
      fetchJSON("/api/v1/roi/summary"),
      fetchJSON("/api/v1/social/stats"),
    ]);

    // ── Social signals stats ──
    const byPlatform = socialStats.by_platform || {};
    document.getElementById("sig-total").textContent = fmt(socialStats.total_7d);
    document.getElementById("sig-ig").textContent    = fmt(byPlatform.instagram);
    document.getElementById("sig-tw").textContent    = fmt(byPlatform.twitter);
    document.getElementById("sig-fb").textContent    = fmt(byPlatform.facebook);

    // ── ROI banner ──
    document.getElementById("roi-label").textContent   = roi.roi_label || "No activity yet";
    document.getElementById("roi-value").textContent   = fmtNgn(roi.value_generated_ngn);
    document.getElementById("roi-api-cost").textContent = fmtNgn(roi.api_cost_ngn);
    document.getElementById("roi-msgs").textContent    = fmt(roi.messages_sent);

    // ── Pending approvals ──
    const aList = document.getElementById("approvals-list");
    const badge = document.getElementById("approval-count-badge");
    const allBar = document.getElementById("approve-all-bar");
    badge.textContent = approvals.length ? `(${approvals.length})` : "";
    allBar.style.display = approvals.length > 1 ? "flex" : "none";
    document.getElementById("approve-all-label").textContent = `${approvals.length} draft${approvals.length !== 1 ? "s" : ""} waiting`;

    if (!approvals.length) {
      aList.innerHTML = '<div class="approvals-empty">No pending drafts — all clear.</div>';
    } else {
      aList.innerHTML = approvals.map(a => {
        const ch      = a.channel || "whatsapp";
        const msg     = a.message || "";
        const escaped = msg.replace(/'/g, "\\'").replace(/\n/g, "\\n");
        const src     = a.source || "maps";
        const plat    = a.platform || "";
        const platIcon = {instagram:"📸", twitter:"🐦", facebook:"📘"}[plat] || "";
        const sourceBadge = src === "social"
          ? `<span class="source-badge source-social">${platIcon} ${plat || "social"}</span>`
          : `<span class="source-badge source-maps">📍 maps</span>`;
        const postCtx = a.post_context
          ? `<div class="post-context">💬 "${a.post_context.slice(0, 160)}${a.post_context.length > 160 ? "…" : ""}"</div>`
          : "";
        const profileLink = a.profile_url
          ? `<a href="${a.profile_url}" target="_blank" style="color:#555;font-size:11px;margin-left:8px;">↗ profile</a>`
          : "";
        return `
          <div class="approval-card">
            <div class="approval-header">
              <span class="approval-name">${a.contact_name || "Unknown"}${sourceBadge}</span>
              <span class="channel-badge channel-${ch}">${ch === "whatsapp" ? "📱 " : "✉️ "}${ch}</span>
            </div>
            <div class="approval-meta">${(a.vertical || "").replace(/_/g," ").toUpperCase()}${profileLink}</div>
            ${postCtx}
            <div class="approval-message">${msg}</div>
            <div class="approval-actions">
              <button class="btn btn-approve" onclick="approveOne('${a.id}')">✓ Approve &amp; Send</button>
              <button class="btn btn-edit"    onclick="openEdit('${a.id}', '${escaped}')">✎ Edit</button>
              <button class="btn btn-skip"    onclick="skipOne('${a.id}')">✕ Skip</button>
            </div>
          </div>`;
      }).join("");
    }

    // ── Summary totals ──
    const all = pipeline.all || {};
    document.getElementById("s-contacted").textContent = fmt(all.contacted);
    document.getElementById("s-replied").textContent   = fmt(all.replied);
    document.getElementById("s-converted").textContent = fmt(all.converted);
    document.getElementById("s-today").textContent     = fmt(all.daily_sent);

    // ── Daily limit bar ──
    const sent  = all.daily_sent || 0;
    const limit = 50; // matches server default
    const pct   = Math.min(100, Math.round((sent / limit) * 100));
    document.getElementById("limit-bar").style.width = pct + "%";
    document.getElementById("limit-label-right").textContent = `${sent} / ${limit}`;

    // ── Verticals grid ──
    const vGrid = document.getElementById("verticals-grid");
    vGrid.innerHTML = "";
    ["real_estate", "recruitment", "events", "fintech", "legal", "logistics"].forEach(v => {
      const s   = pipeline[v] || {};
      const icon = VERTICAL_ICONS[v] || "📋";
      const label = v.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
      vGrid.innerHTML += `
        <div class="vertical-card">
          <h3>${icon} ${label}</h3>
          <div class="v-row"><span class="lbl">Not contacted</span><span class="val">${fmt(s.not_contacted)}</span></div>
          <div class="v-row"><span class="lbl">Contacted</span><span class="val contacted">${fmt(s.contacted)}</span></div>
          <div class="v-row"><span class="lbl">Replied</span><span class="val replied">${fmt(s.replied)}</span></div>
          <div class="v-row"><span class="lbl">Converted</span><span class="val converted">${fmt(s.converted)}</span></div>
          <div class="v-row"><span class="lbl">Opted out</span><span class="val">${fmt(s.opted_out)}</span></div>
          <div class="v-row"><span class="lbl">Sent today</span><span class="val">${fmt(s.daily_sent)}</span></div>
        </div>`;
    });

    // ── Recent replies ──
    const rList = document.getElementById("replies-list");
    if (!replies.length) {
      rList.innerHTML = '<div class="empty">No replies yet — campaigns running tonight at 10pm Lagos time.</div>';
    } else {
      rList.innerHTML = replies.map(r => {
        const intent   = r.intent || "unknown";
        const badgeClass = `intent-badge intent-${intent}`;
        const time = r.received_at ? new Date(r.received_at).toLocaleString("en-NG", { timeZone: "Africa/Lagos" }) : "";
        return `
          <div class="reply-card">
            <div class="reply-header">
              <span class="reply-name">${r.contact_name || r.sender || "Unknown"}</span>
              <span class="${badgeClass}">${INTENT_LABELS[intent] || intent}</span>
            </div>
            <div class="reply-meta">${r.channel ? r.channel.toUpperCase() : ""} &nbsp;·&nbsp; ${time}</div>
            <div class="reply-summary">${r.summary || r.text || ""}</div>
          </div>`;
      }).join("");
    }

    document.getElementById("last-updated").textContent =
      "Last updated: " + new Date().toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos" });

  } catch (err) {
    console.error("Dashboard refresh failed:", err);
  }
}

refresh();
setInterval(refresh, 30000);

// ── Hook Generator ────────────────────────────────────────────────────────────

async function generateHooks() {
  const btn      = document.getElementById("hk-btn");
  const topic    = document.getElementById("hk-topic").value.trim();
  const vertical = document.getElementById("hk-vertical").value;
  const platform = document.getElementById("hk-platform").value;
  const count    = parseInt(document.getElementById("hk-count").value) || 8;
  const client   = document.getElementById("hk-client").value.trim();
  const compRaw  = document.getElementById("hk-competitors").value.trim();
  const competitors = compRaw ? compRaw.split(",").map(s => s.trim()).filter(Boolean) : [];

  if (!topic) { alert("Enter a topic first"); return; }

  btn.textContent = "⏳ Researching & generating…";
  btn.disabled = true;
  document.getElementById("hooks-output").innerHTML = "";
  document.getElementById("trending-pills").style.display = "none";

  try {
    const result = await postJSON("/api/v1/hooks/generate", {
      vertical, topic, platform, count,
      competitor_handles: competitors,
      client_name: client || "default",
    });

    // Trending reference
    if (result.trending_reference && result.trending_reference.length) {
      const pills = document.getElementById("trending-pills");
      pills.style.display = "flex";
      pills.innerHTML = `<span style="font-size:11px;color:#555;align-self:center;margin-right:4px;">TRENDING REF:</span>` +
        result.trending_reference.map(h => `<span class="trending-pill" title="${h}">${h}</span>`).join("");
    }

    // Hooks
    const out = document.getElementById("hooks-output");
    if (!result.hooks || !result.hooks.length) {
      out.innerHTML = '<div class="empty">No hooks generated — check your Apify token.</div>';
      return;
    }
    out.innerHTML = result.hooks.map((h, i) => `
      <div class="hook-card">
        <div class="hook-text">${i + 1}. ${h.hook || h}</div>
        <div class="hook-meta">
          <span class="hook-format">${(h.format || "").replace(/_/g," ")}</span>
          <span class="hook-why">${h.why_it_works || ""}</span>
          <button class="hook-copy" onclick="navigator.clipboard.writeText(${JSON.stringify(h.hook || h)});this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)">Copy</button>
        </div>
      </div>`).join("");

  } catch (err) {
    document.getElementById("hooks-output").innerHTML = `<div class="empty">Error: ${err.message}</div>`;
  } finally {
    btn.textContent = "⚡ Generate Hooks";
    btn.disabled = false;
  }
}

// ── Invoice Collection ────────────────────────────────────────────────────────

async function addInvoice() {
  const btn    = document.getElementById("inv-add-btn");
  const client = document.getElementById("inv-client").value.trim();
  const debtor = document.getElementById("inv-debtor").value.trim();
  const phone  = document.getElementById("inv-phone").value.trim();
  const amount = parseFloat(document.getElementById("inv-amount").value);
  const due    = document.getElementById("inv-due").value;
  const desc   = document.getElementById("inv-desc").value.trim();
  const res    = document.getElementById("inv-add-result");

  const customDaysRaw = document.getElementById("inv-custom-days").value.trim();
  const customTones   = Array.from(document.getElementById("inv-custom-tones").selectedOptions).map(o => o.value);

  if (!client || !debtor || !phone || !amount || !due) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Client, debtor, phone, amount, and due date are required.</div>`;
    res.style.display = "block"; return;
  }

  const body = {
    client_name: client, debtor_name: debtor, debtor_phone: phone,
    amount_ngn: amount, due_date: new Date(due).toISOString(), description: desc,
  };
  if (customDaysRaw) {
    body.custom_reminder_days = customDaysRaw.split(",").map(d => parseInt(d.trim())).filter(n => !isNaN(n));
  }
  if (customTones.length > 0) body.custom_tones = customTones;

  btn.textContent = "Saving…"; btn.disabled = true;
  try {
    const data = await postJSON("/api/v1/invoices/", body);
    res.innerHTML = `<div style="color:#00e5a0;font-size:13px;">✓ Invoice added. ReachNG will send automatic reminders starting on the due date.</div>`;
    // Clear fields
    ["inv-client","inv-debtor","inv-phone","inv-amount","inv-due","inv-desc","inv-custom-days"].forEach(id => {
      document.getElementById(id).value = "";
    });
    loadInvoices();
  } catch (err) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Error: ${err.message}</div>`;
  } finally {
    res.style.display = "block";
    btn.textContent = "+ Add Invoice"; btn.disabled = false;
  }
}

async function loadInvoices() {
  const client = document.getElementById("inv-filter-client").value.trim();
  const params = new URLSearchParams();
  if (client) params.set("client_name", client);

  try {
    const [invoices, stats] = await Promise.all([
      fetch(`/api/v1/invoices/?${params}`).then(r => r.json()),
      fetch(`/api/v1/invoices/stats${client ? "?client_name=" + encodeURIComponent(client) : ""}`).then(r => r.json()),
    ]);

    // Stats bar
    const statsEl = document.getElementById("inv-stats");
    const outstanding = stats.total_outstanding_ngn || 0;
    const paid = stats.total_paid_ngn || 0;
    const rate = stats.collection_rate || 0;
    statsEl.innerHTML = `
      <div class="card" style="background:#111;border:1px solid #222;padding:12px 16px;border-radius:6px;">
        <div style="font-size:20px;color:#ff5c00;font-weight:700;">₦${outstanding.toLocaleString()}</div>
        <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.1em;margin-top:4px;">Outstanding</div>
      </div>
      <div class="card" style="background:#111;border:1px solid #222;padding:12px 16px;border-radius:6px;">
        <div style="font-size:20px;color:#00e5a0;font-weight:700;">₦${paid.toLocaleString()}</div>
        <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.1em;margin-top:4px;">Collected</div>
      </div>
      <div class="card" style="background:#111;border:1px solid #222;padding:12px 16px;border-radius:6px;">
        <div style="font-size:20px;color:#f5c842;font-weight:700;">${rate}%</div>
        <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.1em;margin-top:4px;">Collection Rate</div>
      </div>`;

    // Invoice list
    const listEl = document.getElementById("inv-list");
    if (!invoices.length) {
      listEl.innerHTML = `<div class="empty">No invoices yet.</div>`; return;
    }

    const statusColor = { pending:"#555", reminded:"#ff5c00", followed_up:"#f5c842",
      plan_offered:"#88f", final_notice:"#f44", responded:"#00e5a0", paid:"#00e5a0", written_off:"#333" };

    listEl.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr>
        <th style="text-align:left;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Debtor</th>
        <th style="text-align:left;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Client</th>
        <th style="text-align:right;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Amount</th>
        <th style="text-align:left;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Due</th>
        <th style="text-align:left;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Status</th>
        <th style="text-align:left;color:#555;border-bottom:1px solid #222;padding:6px;font-size:10px;text-transform:uppercase;">Actions</th>
      </tr></thead>
      <tbody>
        ${invoices.map(inv => `
          <tr style="border-bottom:1px solid #1a1a1a;">
            <td style="padding:8px 6px;">${inv.debtor_name}</td>
            <td style="padding:8px 6px;color:#888;">${inv.client_name}</td>
            <td style="padding:8px 6px;text-align:right;color:#ff5c00;">₦${inv.amount_ngn.toLocaleString()}</td>
            <td style="padding:8px 6px;color:#888;">${inv.due_date ? inv.due_date.split("T")[0] : "—"}</td>
            <td style="padding:8px 6px;">
              <span style="color:${statusColor[inv.status]||"#888"};font-size:10px;text-transform:uppercase;letter-spacing:0.1em;">${inv.status.replace(/_/g," ")}</span>
            </td>
            <td style="padding:8px 6px;">
              <div style="display:flex;gap:4px;flex-wrap:wrap;">
                <button onclick="remindNow('${inv.id}')" style="font-size:10px;padding:2px 8px;background:#1a1a00;border:1px solid #333;color:#f5c842;border-radius:4px;cursor:pointer;">Remind</button>
                <button onclick="markInvoicePaid('${inv.id}')" style="font-size:10px;padding:2px 8px;background:#001a0a;border:1px solid #333;color:#00e5a0;border-radius:4px;cursor:pointer;">Paid</button>
                <button onclick="markWrittenOff('${inv.id}')" style="font-size:10px;padding:2px 8px;background:#1a0000;border:1px solid #333;color:#888;border-radius:4px;cursor:pointer;">Write Off</button>
              </div>
            </td>
          </tr>`).join("")}
      </tbody>
    </table>`;
  } catch(err) {
    document.getElementById("inv-list").innerHTML = `<div class="empty" style="color:#ff4444;">Error loading invoices.</div>`;
  }
}

async function remindNow(invoiceId) {
  const tone = prompt("Reminder tone? (polite / firm / payment_plan / final)", "polite");
  if (!tone) return;
  try {
    await postJSON(`/api/v1/invoices/${invoiceId}/remind-now`, { tone });
    alert("Reminder queued.");
    loadInvoices();
  } catch(err) { alert("Error: " + err.message); }
}

async function markInvoicePaid(invoiceId) {
  if (!confirm("Mark this invoice as paid?")) return;
  try {
    await fetch(`/api/v1/invoices/${invoiceId}/paid`, { method: "POST" });
    loadInvoices();
  } catch(err) { alert("Error: " + err.message); }
}

async function markWrittenOff(invoiceId) {
  if (!confirm("Write off this invoice? This cannot be undone.")) return;
  try {
    await fetch(`/api/v1/invoices/${invoiceId}/written-off`, { method: "POST" });
    loadInvoices();
  } catch(err) { alert("Error: " + err.message); }
}

// Load invoices on page load
loadInvoices();

// ── Client Onboarding ─────────────────────────────────────────────────────────

async function createClient() {
  const btn   = document.getElementById("ob-create-btn");
  const name  = document.getElementById("ob-name").value.trim();
  const brief = document.getElementById("ob-brief").value.trim();
  const vertical = document.getElementById("ob-vertical").value;
  const channel  = document.getElementById("ob-channel").value;
  const plan       = document.getElementById("ob-plan").value;
  const city       = document.getElementById("ob-city").value.trim();
  const waAccount  = document.getElementById("ob-wa-account").value.trim();
  const emailAcct  = document.getElementById("ob-email-account").value.trim();
  const res   = document.getElementById("ob-create-result");

  if (!name || !brief) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Client name and brief are required.</div>`;
    res.style.display = "block";
    return;
  }

  btn.textContent = "Saving…"; btn.disabled = true;
  try {
    const data = await postJSON("/api/v1/clients/", {
      name, vertical, brief, preferred_channel: channel, active: true,
      plan: plan || null,
      city: city || null,
      whatsapp_account_id: waAccount || null,
      email_account_id: emailAcct || null,
    });
    res.innerHTML = `<div style="color:#00e5a0;font-size:13px;">✓ Client <strong>${name}</strong> ${data.action}. Now generate their portal link in Step 2.</div>`;
    // Pre-fill step 2 and 3 name fields
    document.getElementById("ob-portal-name").value = name;
    document.getElementById("ob-run-name").value = name;
    document.getElementById("ob-run-vertical").value = vertical;
  } catch (err) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Error: ${err.message}</div>`;
  } finally {
    res.style.display = "block";
    btn.textContent = "✓ Save Client"; btn.disabled = false;
  }
}

async function generatePortal() {
  const btn  = document.getElementById("ob-portal-btn");
  const name = document.getElementById("ob-portal-name").value.trim();
  const res  = document.getElementById("ob-portal-result");

  if (!name) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Enter client name first.</div>`;
    res.style.display = "block";
    return;
  }

  btn.textContent = "Generating…"; btn.disabled = true;
  try {
    const data = await fetch(`/api/v1/portal/generate/${encodeURIComponent(name)}`, { method: "POST" }).then(r => r.json());
    const url  = window.location.origin + data.portal_url;
    res.innerHTML = `
      <div style="background:#0d1a0d;border:1px solid #1a3a1a;border-radius:8px;padding:14px 16px;">
        <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Portal Link for ${name}</div>
        <div style="display:flex;align-items:center;gap:10px;">
          <input value="${url}" readonly style="flex:1;background:#111;border:1px solid #2a2a2a;border-radius:6px;padding:8px 10px;color:#00e5a0;font-size:13px;font-family:monospace;" onclick="this.select()" />
          <button class="btn" style="background:#1a3a1a;border:1px solid #2a4a2a;white-space:nowrap;" onclick="navigator.clipboard.writeText('${url}').then(()=>this.textContent='Copied!').catch(()=>{})">Copy</button>
        </div>
        <p style="font-size:11px;color:#555;margin-top:8px;">Share this link with ${name}. No login required.</p>
      </div>`;
  } catch (err) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Error: ${err.message}</div>`;
  } finally {
    res.style.display = "block";
    btn.textContent = "🔗 Generate Portal"; btn.disabled = false;
  }
}

async function runClientCampaign() {
  const btn      = document.getElementById("ob-run-btn");
  const name     = document.getElementById("ob-run-name").value.trim();
  const vertical = document.getElementById("ob-run-vertical").value;
  const max      = parseInt(document.getElementById("ob-run-max").value) || 30;
  const dryRun   = document.getElementById("ob-run-dryrun").checked;
  const res      = document.getElementById("ob-run-result");

  if (!name) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Enter client name first.</div>`;
    res.style.display = "block";
    return;
  }

  btn.textContent = "⏳ Running…"; btn.disabled = true;
  try {
    const result = await postJSON("/api/v1/campaigns/run", {
      vertical, max_contacts: max, dry_run: dryRun, client_name: name,
    });
    const rows = Object.entries(result).map(([k, v]) => {
      const label = k.replace(/_/g, " ");
      const val   = typeof v === "boolean" ? (v ? "yes" : "no") : v;
      return `<div class="v-row"><span class="lbl">${label}</span><span class="val">${val}</span></div>`;
    }).join("");
    res.innerHTML = `
      <div style="background:#0d0d0d;border:1px solid #222;border-radius:10px;padding:16px 20px;">
        <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px;">
          ${name} — ${vertical.replace(/_/g," ")} ${dryRun ? "(dry run)" : "(live)"}
        </div>
        ${rows}
      </div>`;
    if (!dryRun) refresh();
  } catch (err) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Error: ${err.message}</div>`;
  } finally {
    res.style.display = "block";
    btn.textContent = "▶ Run"; btn.disabled = false;
  }
}

// ── Export Contacts ────────────────────────────────────────────────────────────

function exportContacts() {
  const vertical = document.getElementById("exp-vertical").value;
  const status   = document.getElementById("exp-status").value;
  const params   = new URLSearchParams();
  if (vertical) params.set("vertical", vertical);
  if (status)   params.set("status", status);
  const url = `/api/v1/contacts/export?${params.toString()}`;
  // Trigger browser download — no JS fetch needed
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ── Run Campaign ──────────────────────────────────────────────────────────────

async function runCampaign() {
  const btn      = document.getElementById("rc-btn");
  const vertical = document.getElementById("rc-vertical").value;
  const max      = parseInt(document.getElementById("rc-max").value) || 10;
  const dryRun   = document.getElementById("rc-dryrun").checked;
  const res      = document.getElementById("rc-result");

  btn.textContent = "⏳ Running…";
  btn.disabled = true;
  res.style.display = "none";

  try {
    const result = await postJSON("/api/v1/campaigns/run", {
      vertical, max_contacts: max, dry_run: dryRun,
    });

    const rows = Object.entries(result).map(([k, v]) => {
      const label = k.replace(/_/g, " ");
      const val   = typeof v === "boolean" ? (v ? "yes" : "no") : v;
      return `<div class="v-row"><span class="lbl">${label}</span><span class="val">${val}</span></div>`;
    }).join("");

    res.innerHTML = `
      <div style="background:#0d0d0d;border:1px solid #222;border-radius:10px;padding:16px 20px;">
        <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px;">
          Result — ${vertical.replace(/_/g," ")} ${dryRun ? "(dry run)" : "(live)"}
        </div>
        ${rows}
      </div>`;
    res.style.display = "block";
    if (!dryRun) refresh();
  } catch (err) {
    res.innerHTML = `<div class="empty" style="color:#ff4444;">Error: ${err.message}</div>`;
    res.style.display = "block";
  } finally {
    btn.textContent = "▶ Run";
    btn.disabled = false;
  }
}
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=_HTML)
