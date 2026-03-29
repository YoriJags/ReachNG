"""
Live pipeline dashboard — single HTML page, auto-refreshes every 30 seconds.
Served at GET /dashboard
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

_HTML = """<!DOCTYPE html>
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

  .empty { color: #333; font-size: 14px; text-align: center; padding: 40px; }

  #last-updated { font-size: 11px; color: #333; text-align: right; margin-top: 48px; }
</style>
</head>
<body>

<header>
  <div class="logo">Reach<span>NG</span></div>
  <div class="live-badge"><span class="status-dot"></span> Live — refreshes every 30s</div>
</header>

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

<!-- Recent replies -->
<p class="section-title">Recent Replies</p>
<div class="replies-list" id="replies-list">
  <div class="empty">Loading…</div>
</div>

<div id="last-updated"></div>

<script>
const VERTICAL_ICONS = { real_estate: "🏠", recruitment: "👥", events: "🎉" };
const INTENT_LABELS  = { interested:"Interested", not_now:"Not Now", opted_out:"Opted Out", referral:"Referral", question:"Question", unknown:"Unknown" };

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function fmt(n) { return n === undefined || n === null ? "0" : String(n); }

async function refresh() {
  try {
    const [pipeline, replies] = await Promise.all([
      fetchJSON("/api/v1/contacts/pipeline"),
      fetchJSON("/api/v1/contacts/replies?limit=10"),
    ]);

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
    ["real_estate", "recruitment", "events"].forEach(v => {
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
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=_HTML)
