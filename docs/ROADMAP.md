# Product Roadmap

## Version Strategy

| Version | Theme | Status |
|---|---|---|
| v0.1.0 | Foundation — static frontend, full demo capability | Complete |
| v0.2.0 | Backend — real auth, real data, real file uploads | Planned Q2 2026 |
| v0.3.0 | Integrations — live ERP and system connections | Planned Q3 2026 |
| v1.0.0 | Production — full commercial launch, first paying clients | Planned Q4 2026 |
| v1.x | Intelligence layer — proprietary models and benchmarking | 2027 |

---

## v0.1.0 — Foundation (Current)

**Status:** Complete — March 2026

### Delivered

- [x] Marketing site with full positioning around operational intelligence
- [x] Investment case section with before/after automation comparisons
- [x] Client intake form with file upload and ROI-qualifying fields
- [x] Client portal with 9-digit authentication
- [x] Dashboard: KPI cards, trend chart, live activity feed, module cards
- [x] Module modals: KPIs, 6-month bar chart, activity log
- [x] Data upload page: completeness score, categorised uploads, security messaging
- [x] Project tracker: 5-phase timeline with task-level detail
- [x] Standalone dashboard demo for sales use
- [x] Full documentation suite (README, CHANGELOG, ARCHITECTURE, BUSINESS_MODEL, CLIENT_PORTAL, ROADMAP)
- [x] Git repository with professional commit structure

---

## v0.2.0 — Backend (Planned Q2 2026)

**Theme:** Replace all demo data with real server-side data. Make the portal production-ready for first paying clients.

### Backend API (FastAPI + PostgreSQL)

- [ ] `POST /api/auth/verify` — validate client code against database, return JWT
- [ ] `GET /api/client/profile` — return client name, plan, account manager
- [ ] `GET /api/client/dashboard` — return KPIs, 6-month trend data
- [ ] `GET /api/client/modules` — return all active automations with current metrics
- [ ] `GET /api/client/modules/:id` — return full module detail (KPIs, chart data, activity log)
- [ ] `GET /api/client/activity` — return live activity feed
- [ ] `GET /api/client/files` — return uploaded files with processing status
- [ ] `POST /api/client/upload` — multipart upload to S3 (UK region, AES-256)
- [ ] `GET /api/client/tracker` — return project phases and task states
- [ ] `GET /api/admin/*` — internal Backbone AI team management endpoints

### Authentication

- [ ] 9-digit code stored as bcrypt hash in PostgreSQL
- [ ] JWT tokens: RS256, 8-hour expiry
- [ ] Refresh token rotation
- [ ] Failed attempt rate limiting (5 attempts → 15 minute lockout)
- [ ] Session restoration on page refresh via `sessionStorage`

### Database Schema

```sql
clients             — client profile, plan, account manager
client_codes        — hashed access codes
automations         — active automation modules per client
savings_log         — daily savings records per module
activity_feed       — real-time event log per client
uploaded_files      — file metadata, S3 key, processing status
project_phases      — engagement phases
project_tasks       — individual tasks within phases
insights            — AI-generated operational insights per client
```

### Infrastructure

- [ ] AWS deployment (eu-west-2 for GDPR compliance)
- [ ] PostgreSQL on RDS
- [ ] File storage on S3 with server-side AES-256 encryption
- [ ] CloudFront CDN for static assets
- [ ] SSL certificate (Let's Encrypt or ACM)
- [ ] Basic monitoring: Sentry for errors, Datadog for uptime

### Frontend updates

- [ ] Replace all `CLIENTS {}` and `MODULES {}` static objects with `fetch()` API calls
- [ ] Add loading states to all data-fetching operations
- [ ] Add error states (expired token → redirect to login, API error → user-friendly message)
- [ ] Hash-based routing for deep linking (`/client#dashboard`, `/client#upload`)
- [ ] Real file upload progress indicator (with presigned S3 URLs)
- [ ] WebSocket connection for live activity feed

### Admin Panel

- [ ] Internal web interface for Backbone AI team
- [ ] Create/manage client accounts and codes
- [ ] Update project task statuses
- [ ] Add activity log entries
- [ ] Upload savings data
- [ ] Add AI-generated insights

---

## v0.3.0 — Integrations (Planned Q3 2026)

**Theme:** Connect to clients' real systems to pull live operational data automatically.

### ERP & Accounting Integrations

- [ ] Sage 50 / Sage 200 export connector (file-based)
- [ ] Xero API integration (invoices, purchase orders)
- [ ] QuickBooks API integration
- [ ] SAP export processing pipeline
- [ ] Generic CSV/Excel ingestion pipeline with column mapping UI

### Operational System Integrations

- [ ] Google Sheets / Microsoft Excel Online (live sync)
- [ ] Fleet management API connectors (Samsara, Verizon Connect, Webfleet)
- [ ] WMS connectors (Mintsoft, Peoplevox)
- [ ] Generic REST API connector framework

### AI Processing Pipeline

- [ ] Invoice processing AI: document extraction (PDF → structured JSON)
- [ ] Anomaly detection: rule-based + statistical thresholds
- [ ] Route optimisation: integration with mapping APIs (Google Maps Platform, HERE)
- [ ] Quality report generation: template + data merge pipeline
- [ ] Compliance document generation: structured template system

### Data Pipeline

- [ ] Automated nightly data ingestion from connected systems
- [ ] Data validation and cleaning pipeline
- [ ] Savings calculation engine: compare automated vs. historical manual metrics
- [ ] Alerting system: detect anomalies and surface to insights feed

---

## v1.0.0 — Production Launch (Planned Q4 2026)

**Theme:** Full commercial readiness. First paying clients onboarded on the live platform.

### Commercial readiness

- [ ] Stripe integration for automated invoicing (retainer + performance share)
- [ ] Contract management (DocuSign integration)
- [ ] Client onboarding email sequence (setup fee paid → portal activated → welcome email)
- [ ] SLA monitoring: uptime, API response time, data freshness

### Security & Compliance

- [ ] Penetration testing (external firm)
- [ ] ICO registration
- [ ] Privacy policy and terms of service
- [ ] GDPR Data Processing Agreement template for clients
- [ ] SOC 2 Type I preparation (if enterprise clients require it)

### Operations

- [ ] Internal Slack bot: new client signup notifications, savings milestones, alerts
- [ ] Weekly automated client email: "Your Backbone AI Week in Numbers"
- [ ] Account manager dashboard: all clients, task statuses, outstanding items
- [ ] Automated monthly performance report (PDF generation + email delivery)

---

## v1.x — Intelligence Layer (2027)

**Theme:** Move from automation to genuine proprietary intelligence.

### Sector Benchmarking Database

- [ ] Anonymised aggregate metrics across all manufacturing clients
- [ ] Anonymised aggregate metrics across all logistics clients
- [ ] Benchmark report generation: "How does your operation compare to peers?"
- [ ] Benchmark-based sales tool: calculate prospect's inefficiency before first call

### Proprietary AI Models

- [ ] Fine-tune base LLM on UK manufacturing and logistics domain data
- [ ] ISO 9001 and HSE compliance document understanding
- [ ] UK logistics regulatory framework (DVSA, operator licensing)
- [ ] Manufacturing quality control classification model (defect type identification)
- [ ] Demand forecasting model: trained on aggregated client order history

### Advanced Automations

- [ ] Predictive maintenance: use equipment usage data to predict failures
- [ ] Dynamic pricing intelligence: surface margin optimisation opportunities
- [ ] Customer delivery intelligence: B2B2C tracking portal for logistics clients' customers
- [ ] Automated supplier negotiation briefings: data-backed negotiation points

### Mobile Application

- [ ] iOS and Android app for site managers and logistics controllers
- [ ] Push notifications for critical alerts (stockout risk, supplier issue, compliance deadline)
- [ ] Quick-access dashboard for on-the-go KPI review
- [ ] Voice-input for field data capture (quality observations, delivery notes)

### Platform Expansion

- [ ] Construction vertical launch (CDM compliance, site reporting, subcontractor management)
- [ ] Legal services vertical launch (document review, contract analysis)
- [ ] White-label option: sell the platform under partner brands

---

## Principles Governing Prioritisation

1. **Revenue first.** Features that directly enable client acquisition or retention take priority over internal tooling.

2. **Depth over breadth.** Go deeper in manufacturing and logistics before expanding to new verticals. A business that's excellent in two sectors beats one that's mediocre in ten.

3. **Data is the moat.** Every architecture decision should prioritise collecting, structuring, and retaining high-quality operational data. This is the asset that becomes more valuable with every client.

4. **Simplicity scales.** A feature that can be explained in one sentence to a client is always preferable to one that requires a training session. The intelligence should be in the system, not in the client's head.

5. **Outcomes over activity.** The roadmap is assessed against client savings generated, not features shipped.

---

*Document version: 1.0 — March 2026*
