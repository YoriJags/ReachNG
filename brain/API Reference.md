---
tags: [reachng]
---
# API Reference

[[Home]] | [[Architecture]] | [[Ops]]

> All routes require HTTP Basic Auth unless noted.
> Base URL: `https://www.reachng.ng`

---

## Campaigns

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/campaigns` | List all campaigns |
| `POST` | `/api/v1/campaigns` | Create + run campaign |
| `GET` | `/api/v1/campaigns/{id}` | Get campaign detail |

---

## Contacts

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/contacts` | List contacts |
| `GET` | `/api/v1/contacts/{id}` | Get contact detail |
| `PATCH` | `/api/v1/contacts/{id}` | Update contact status |
| `DELETE` | `/api/v1/contacts/{id}` | Delete contact |

---

## Clients

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/clients` | List clients |
| `POST` | `/api/v1/clients` | Add client |
| `GET` | `/api/v1/clients/{id}` | Get client |
| `PATCH` | `/api/v1/clients/{id}` | Update client |

---

## Invoice Chaser

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/invoice-chaser/parse` | Upload PDF → extract invoice fields (Gemini) |
| `POST` | `/api/v1/invoice-chaser/send-reminder` | Send WhatsApp reminder with tone escalation |
| `GET` | `/api/v1/invoice-chaser/history/{client_name}` | List chased invoices for client |

---

## Approvals (HITL)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/approvals` | List pending approvals |
| `POST` | `/api/v1/approvals/{id}/approve` | Approve + send message |
| `POST` | `/api/v1/approvals/{id}/reject` | Reject message |
| `PATCH` | `/api/v1/approvals/{id}` | Edit message text |

---

## ROI

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/roi` | ROI summary |
| `POST` | `/api/v1/roi/event` | Log ROI event (conversion, revenue) |

---

## Data (RAG)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/data/ingest` | Upload file (PDF/CSV/XLSX) for RAG |
| `POST` | `/api/v1/data/query` | Query ingested data |

---

## Portal (No Basic Auth — token-gated)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/portal/{token}` | Client portal |
| `GET` | `/portal/demo` | Public demo portal (no auth) |

---

## Dashboard (Basic Auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/dashboard` | Master dashboard HTML |

---

## Debug (Basic Auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/debug/maps` | Raw Google Places API test |
| `GET` | `/debug/apollo` | Raw Apollo API test |
| `GET` | `/debug/apify` | Raw Apify TikTok scraper test |

---

## Health (No Auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | DB ping + status |

---

## MCP

| Method | Path | Description |
|--------|------|-------------|
| `*` | `/mcp` | MCP server — exposes tools to Claude |

---

## Docs

| Path | Description |
|------|-------------|
| `/docs` | Swagger UI (auto-generated) |
| `/redoc` | ReDoc (auto-generated) |
