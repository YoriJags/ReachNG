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
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=_HTML)
