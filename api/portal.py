"""
Client Portal — token-gated read-only dashboard for each paying ReachNG client.
Each client gets a unique URL: /portal/{token}
Shows their contacts, outreach stats, and ROI.
"""
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from bson import ObjectId
from database import get_contacts, get_outreach_log, get_db
from tools.roi import get_roi_summary

router = APIRouter(prefix="/portal", tags=["Portal"])


def get_clients():
    return get_db()["clients"]


# ─── Token management ─────────────────────────────────────────────────────────

def generate_portal_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_client_token(client_name: str) -> str:
    """Generate and store a portal token if the client doesn't have one yet."""
    clients = get_clients()
    client = clients.find_one({"name": {"$regex": f"^{client_name}$", "$options": "i"}})
    if not client:
        raise ValueError(f"Client '{client_name}' not found")
    if client.get("portal_token"):
        return client["portal_token"]
    token = generate_portal_token()
    clients.update_one(
        {"_id": client["_id"]},
        {"$set": {"portal_token": token, "portal_created_at": datetime.now(timezone.utc)}},
    )
    return token


def _get_client_by_token(token: str) -> dict | None:
    return get_clients().find_one({"portal_token": token, "active": True})


# ─── API endpoints ────────────────────────────────────────────────────────────

@router.post("/generate/{client_name}")
async def generate_portal_link(client_name: str):
    """Generate (or return existing) portal token for a client."""
    try:
        token = ensure_client_token(client_name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "client": client_name,
        "portal_token": token,
        "portal_url": f"/portal/{token}",
    }


@router.get("/data/{token}")
async def get_portal_data(token: str):
    """JSON data endpoint for the portal — used by the HTML dashboard."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found or client inactive")

    vertical = client.get("vertical")
    client_name = client["name"]

    # Contacts scoped to this client only — prevents cross-client data leak
    contacts = list(
        get_contacts()
        .find({"vertical": vertical, "client_name": client_name})
        .sort("lead_score", -1)
        .limit(100)
    )
    for c in contacts:
        c["id"] = str(c.pop("_id"))
        for f in ("created_at", "last_contacted_at", "updated_at", "next_followup_at"):
            if hasattr(c.get(f), "isoformat"):
                c[f] = c[f].isoformat()

    # Status counts
    from tools.memory import get_pipeline_stats
    stats = get_pipeline_stats(vertical=vertical)

    # ROI
    roi = get_roi_summary(days=30, client_name=client_name)

    return {
        "client": client_name,
        "vertical": vertical,
        "stats": stats,
        "roi": roi,
        "contacts": contacts,
    }


@router.get("/demo", response_class=HTMLResponse)
async def demo_portal(request: Request):
    """Public demo portal — shows realistic sample data for pitch/sales purposes."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal_demo.html")


@router.get("/{token}", response_class=HTMLResponse)
async def client_portal(token: str, request: Request):
    """Render the client portal HTML dashboard."""
    client = _get_client_by_token(token)
    if not client:
        raise HTTPException(404, "Portal not found")

    client_name = client["name"]
    vertical = client.get("vertical", "").replace("_", " ").title()

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "portal.html", {"token": token, "client_name": client_name, "vertical": vertical})


# ─── Portal HTML ──────────────────────────────────────────────────────────────

def _portal_html(token: str, client_name: str, vertical: str, demo: bool = False) -> str:
    data_loader = "const data = DEMO_DATA;" if demo else f"const data = await fetch('/portal/data/{token}').then(r => r.json());"
    demo_banner = '<p style="background:#1a1000;color:#f5c842;font-size:11px;padding:8px 16px;margin-bottom:24px;border:1px solid #f5c842;letter-spacing:0.1em;">DEMO — Sample data for illustration purposes</p>' if demo else ""
    return rf"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{client_name} — ReachNG Portal</title>
<style>
  :root {{
    --bg: #0a0a0a; --card: #111; --border: #222;
    --orange: #ff5c00; --green: #00e5a0; --gold: #f5c842;
    --white: #f0f0f0; --muted: #888; --dim: #444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--white); font-family: 'Courier New', monospace; padding: 32px; min-height: 100vh; }}
  h1 {{ font-size: 22px; color: var(--orange); margin-bottom: 4px; }}
  .sub {{ color: var(--muted); font-size: 12px; letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 32px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); padding: 16px; border-radius: 4px; }}
  .card .val {{ font-size: 28px; font-weight: 700; }}
  .card .lbl {{ font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }}
  .orange {{ color: var(--orange); }} .green {{ color: var(--green); }} .gold {{ color: var(--gold); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: var(--muted); border-bottom: 1px solid var(--border); padding: 8px 6px; font-weight: normal; text-transform: uppercase; letter-spacing: 0.1em; font-size: 10px; }}
  td {{ padding: 8px 6px; border-bottom: 1px solid #1a1a1a; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; }}
  .badge-new {{ background: #1a2a1a; color: var(--green); }}
  .badge-contacted {{ background: #2a1a00; color: var(--orange); }}
  .badge-replied {{ background: #1a1a2a; color: #88f; }}
  .badge-converted {{ background: #002a1a; color: var(--green); }}
  .badge-opted_out {{ background: #2a1a1a; color: #f44; }}
  .roi-bar {{ background: var(--card); border: 1px solid var(--border); padding: 20px; border-radius: 4px; margin-bottom: 32px; }}
  .roi-label {{ font-size: 14px; color: var(--green); margin-top: 8px; }}
  #loading {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<h1>{client_name}</h1>
<p class="sub">{vertical} &nbsp;·&nbsp; Powered by ReachNG &nbsp;·&nbsp; Last 30 days</p>

{demo_banner}
<div id="loading">Loading your dashboard…</div>
<div id="content" style="display:none;">
  <div class="grid" id="stats-grid"></div>
  <div class="roi-bar" id="roi-bar"></div>
  <h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:0.15em;margin-bottom:12px;">Your Leads</h2>
  <table>
    <thead>
      <tr>
        <th>Business</th><th>Category</th><th>Phone</th><th>Rating</th><th>Score</th><th>Status</th>
      </tr>
    </thead>
    <tbody id="contacts-tbody"></tbody>
  </table>
</div>

<script>
const DEMO_DATA = {{
  stats: {{ contacted: 47, replied: 12, converted: 3, daily_sent: 18 }},
  roi: {{ messages_sent: 47, value_generated_ngn: 450000, roi_percent: "9.0", roi_label: "Strong pipeline — 3 deals in progress" }},
  contacts: [
    {{ name: "Landmark Africa Properties", category: "Real Estate", phone: "+2348012345678", rating: 4.7, lead_score: 91, status: "replied" }},
    {{ name: "Ocean Bay Developers", category: "Property Developer", phone: "+2348023456789", rating: 4.5, lead_score: 86, status: "contacted" }},
    {{ name: "Lekki Phase 1 Realty", category: "Real Estate", phone: "+2348034567890", rating: 4.3, lead_score: 82, status: "converted" }},
    {{ name: "VI Premium Homes", category: "Real Estate", phone: "+2348045678901", rating: 4.1, lead_score: 78, status: "contacted" }},
    {{ name: "Ikoyi Luxury Estates", category: "Property Developer", phone: "+2348056789012", rating: 4.8, lead_score: 94, status: "replied" }},
    {{ name: "Ajah New Town Developers", category: "Real Estate", phone: "+2348067890123", rating: 3.9, lead_score: 71, status: "new" }},
    {{ name: "Greenfield Homes Lagos", category: "Real Estate", phone: "+2348078901234", rating: 4.2, lead_score: 79, status: "contacted" }},
    {{ name: "Prime Properties NG", category: "Property Developer", phone: "+2348089012345", rating: 4.6, lead_score: 88, status: "converted" }},
  ]
}};

async function load() {{
  {data_loader}
  document.getElementById('loading').style.display = 'none';
  document.getElementById('content').style.display = '';

  // Stats
  const s = data.stats;
  const statsGrid = document.getElementById('stats-grid');
  const statItems = [
    {{ val: s.contacted || 0, lbl: 'Contacted', cls: 'orange' }},
    {{ val: s.replied || 0,   lbl: 'Replied',   cls: 'green' }},
    {{ val: s.converted || 0, lbl: 'Converted', cls: 'gold' }},
    {{ val: s.daily_sent || 0, lbl: 'Sent Today', cls: 'white' }},
  ];
  statsGrid.innerHTML = statItems.map(i =>
    `<div class="card"><div class="val ${{i.cls}}">${{i.val}}</div><div class="lbl">${{i.lbl}}</div></div>`
  ).join('');

  // ROI
  const roi = data.roi;
  document.getElementById('roi-bar').innerHTML = `
    <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">ROI Summary · Last 30 Days</div>
    <div class="roi-label">${{roi.roi_label || 'No activity yet'}}</div>
    <div style="display:flex;gap:32px;margin-top:12px;">
      <div><div style="font-size:18px;color:var(--orange);">${{roi.messages_sent}}</div><div style="font-size:10px;color:var(--muted);">Messages Sent</div></div>
      <div><div style="font-size:18px;color:var(--green);">₦${{(roi.value_generated_ngn||0).toLocaleString()}}</div><div style="font-size:10px;color:var(--muted);">Value Generated</div></div>
      <div><div style="font-size:18px;color:var(--gold);">${{roi.roi_percent}}x</div><div style="font-size:10px;color:var(--muted);">ROI</div></div>
    </div>
  `;

  // Contacts table
  const tbody = document.getElementById('contacts-tbody');
  tbody.innerHTML = data.contacts.map(c => `
    <tr>
      <td>${{c.name}}</td>
      <td style="color:var(--muted)">${{c.category || '—'}}</td>
      <td style="color:var(--muted)">${{c.phone || '—'}}</td>
      <td>${{c.rating ? '★ ' + c.rating : '—'}}</td>
      <td><span style="color:var(--orange)">${{c.lead_score ?? '—'}}</span></td>
      <td><span class="badge badge-${{c.status}}">${{c.status}}</span></td>
    </tr>
  `).join('');
}}
load();
</script>
</body>
</html>"""
