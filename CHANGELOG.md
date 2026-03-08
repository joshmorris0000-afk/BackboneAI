# Changelog

All notable changes to the Backbone AI platform are documented here.

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version — breaking changes
- **MINOR** version — new features, backwards compatible
- **PATCH** version — bug fixes and minor improvements

---

## [0.3.6] — 2026-03-08

### Added — Client Portal: Inventory Forecast detail section (Feature 7)

- `autoDetail` for `inventory` module: 12-SKU Stock Watch table
- Columns: SKU, Item, Current Stock, Daily Usage, Days Remaining (colour-coded), Action
- Colour coding: <7 days remaining `.dt-critical` (red), 7–14 days `.dt-warn` (orange), 14+ days `.dt-ok` (green)
- SKUs include corrugated boxes, stretch wrap, thermal labels, tape, foam protectors, bubble wrap, cardboard boxes, cable ties, label pouches, silica gel sachets, Line 4 consumables, anti-static bags
- 3 stat cards: zero stockouts this month, 97% forecast accuracy, £4,200 capital freed from overstock

---

## [0.3.5] — 2026-03-08

### Added — Client Portal: Compliance Docs detail section (Feature 6)

- `autoDetail` for `compliance` module: 8-document Document Library table
- Columns: Document Name, Type, Period, Generated date, Review Time, Status badge, Download button
- Status badges: Ready (green), Reviewed (blue), Scheduled (grey)
- Download buttons call `downloadReport()` — opens `sample-report.html?print`
- Documents: March ops report, March compliance pack, driver hours & WTD, February ops report, vehicle inspection, operator licence check, annual audit pack, HSE risk assessment
- Upcoming section: 3 next scheduled auto-drafts with dates

---

## [0.3.4] — 2026-03-08

### Added — Client Portal: Supplier Intelligence detail section (Feature 5)

- `autoDetail` for `suppliers` module: 14-row Supplier Scorecards table
- Columns: Supplier Name, On-Time %, Invoice Accuracy, Reliability Trend (↑↓→), Status badge
- Status badges: Good (green), Watch (orange), At Risk (red)
- Midlands Freight Co highlighted as At Risk at 72% on-time
- City Haulage Ltd and Direct Logistics Co flagged as Watch
- 3 active alert cards below the table with specific context and recommended actions

---

## [0.3.3] — 2026-03-08

### Added — Client Portal: Route Optimisation detail section (Feature 4)

- `autoDetail` for `routes` module: 10-row This Week's Routes table
- Columns: Vehicle, Route (origin → destinations), Original Miles, Optimised Miles, Saving £, Status
- Status badges: Completed (green), In Progress (blue)
- 3 stat cards: 94% on-time this week, 447 miles saved this week, 20 vehicles actively optimised

---

## [0.3.2] — 2026-03-08

### Added — Client Portal: Invoice Processing detail section (Feature 3)

- `autoDetail` property on `invoices` MODULES entry containing enriched detail HTML
- `<div id="autoDetailSection">` added to `page-automation` template; `loadAutoPage()` now injects `m.autoDetail || ''` into this element
- 10-row Recent Invoices table: Invoice #, Supplier, Amount, PO Match, Status badge (Approved/Flagged/Pending), Time Saved
- Status badges: `.dt-approved` (green), `.dt-flagged` (red), `.dt-pending` (grey)
- 3 stat cards below the table: Avg processing time 2.3 min, Duplicate invoices blocked 3, Error recovery rate 100%

---

## [0.3.1] — 2026-03-08

### Added — Client Portal: Reports Page (`client.html`)

- New `page-reports` with a 6-card grid of monthly reports for Whitfield Logistics
- Report cards: March Operations Report (Ready), March Compliance Pack (Ready), February Supplier Scorecard (Sent), February Fleet Efficiency (Sent), February Operations Report (Sent), March Supplier Scorecard (Scheduled)
- Each card shows report name, description, generation date, page count, and status badge (`rbadge-ready`, `rbadge-sent`, `rbadge-scheduled`)
- Download PDF button opens `sample-report.html?print` in a new tab (triggers Save as PDF dialog)
- Preview button opens an inline modal with per-report KPI summaries (6 data points per report)
- Report preview overlay (`report-preview-overlay`, `report-preview-modal`) with click-outside and Escape key close
- JS functions: `previewReport()`, `closeReportPreview()`, `closeReportPreviewDirect()`, `downloadReport()`
- `REPORT_PREVIEWS` data object keyed by report title with label/value pairs
- `reports` added to titles map: `['Performance Reports', 'Monthly reports and downloadable summaries']`

---

## [0.3.0] — 2026-03-08

### Added — Client Portal: Insights Page (`client.html`)

- New `page-insights` with 8 AI-surfaced insight cards specific to Whitfield Logistics Ltd
- Cards cover: Midlands Freight reliability warning, invoice discrepancy pattern, Tuesday failed-drop opportunity, packing stock reorder opportunity, Vehicle 12 routing opportunity, Northern Fuel improvement, invoice accuracy record, and compliance pack completion
- Filter bar with 4 buttons: All insights / Warnings / Opportunities / Positives — `filterInsights(type, btn)` hides/shows cards by `data-type` attribute
- `markInsightDone(btn)` marks cards as actioned with visual fade and disabled state
- Severity system: `.sev-warning` (orange left border), `.sev-opportunity` (blue left border), `.sev-positive` (green left border)
- CSS: `.ifilter`, `.ifilter.active`, `.insight-card`, `.insight-severity`, `.insight-action-btn`, `.insight-action-btn.actioned`, `.insights-full-list`
- Added "Overview" section label to sidebar nav above Dashboard
- Added `💡 Insights` nav button (before Services), `📈 Reports` nav button
- `insights` added to titles map: `['Operational Insights', 'AI-surfaced patterns from your data this month']`
- Data-table shared CSS added: `.data-table`, `.dt-badge` variants, `.stat-cards-row`, `.stat-card-sm`, `.alert-cards-row`, `.alert-card`, `.upcoming-section` (used by features 3–7)

---

## [0.2.1] — 2026-03-07

### Added — Sample Report (`sample-report.html`)

- Print-optimised operations report for Whitfield Logistics Ltd (March 2026)
- Sections: Executive Summary KPIs, Automation Performance table, Anomalies & Findings, Supplier Scorecard with visual bars, Recommendations list, Financial Summary, April preview
- Fixed print bar at top of screen with "Save as PDF" button triggering `window.print()`
- `@media print` hides the print bar and sets `@page` margins for clean output
- `print-color-adjust: exact` on all coloured elements so backgrounds survive the print pipeline
- Auto-triggers print dialog if `?print` query param is present (used by the dashboard download button)

### Fixed — Dashboard Demo (`dashboard.html`)

- `downloadReport()` now opens `sample-report.html?print` in a new tab, which immediately triggers the browser Save as PDF dialog — previously was a cosmetic-only toast
- "Last 30 days" static label replaced with a functional `<select>` dropdown offering 30 / 60 / 90 / 180 / 365 day periods
- `setDateRange()` function updates the trend chart labels and datasets live on selection; chart stored as `window._dashChart` to make it globally accessible

---

## [0.2.0] — 2026-03-07

### Added — Admin Panel (`admin.html`)

- Internal team panel with amber accent theme (`--admin-accent: #f59e0b`) to visually distinguish from client portal
- Four pages: Overview, Client Accounts, Upload Queue, System Requests
- Overview: live MRR summary, revenue breakdown table (retainer + performance share per client), action-required list, activity feed
- Client Accounts: filterable table by status/plan/account manager, completeness progress bars per client
- Upload Queue: filterable by client/category/status, inline `setUploadStatus()` action buttons
- System Requests: tabbed view (all / needs action / connected / custom builds), mark-connected and chase-client actions
- `updateBadges()` function: updates sidebar badge counts on every state change
- Demo data: 3 clients (Whitfield Logistics, Thornton Manufacturing, Northern Freight), 12 upload entries, 9 system request entries

### Added — Services Page (`services.html`)

- Full service guide covering all three retainer tiers (Pilot, Scale, Backbone) with detailed feature lists
- Add-on module table: 7 modules with description, target audience, and availability status
- Project work grid: Process Efficiency Audit, ERP & System Selection, Custom Integration Build, Data Quality Audit
- "Three ways to start" entry-point section (Free Audit, Project First, Direct to Retainer)
- Full SEO meta, Open Graph tags, non-blocking fonts, nav, footer

### Added — Audit Landing Page (`audit.html`)

- Free 2-week operations audit application page
- Inline application form: name, email, company, sector, size, current systems, main operational problem
- 5-step audit process breakdown with time expectations at each stage
- Illustrative examples section showing categories of issues audits can surface (clearly labelled as illustrative — no fabricated case studies or invented savings figures)
- Eligibility grid: good fit vs. not a good fit
- Form success state on submission
- SEO meta, OG tags, non-blocking fonts

### Added — Marketing Site Enhancements (`index.html`)

**Services Section**
- Three-card services overview between Comparison and Pricing sections
- Cards: Core Retainer (what's in every plan), Specialist Modules (billable add-ons), Project Work (one-offs)
- Six-card add-on spotlight grid beneath the tier cards

**Examples Section**
- Ten illustrative systems showing common manufacturing/logistics pain points automated
- Honest framing — no fabricated statistics or invented client outcomes
- Two intro blocks: "Hours → Minutes" and "Built once. Runs forever."
- Each system card numbered, colour-coded, with problem description and honest outcome label

**Nav & Footer**
- Nav reordered to match page scroll order: What We Do → How It Works → Services → Examples → Pricing → Client Login → Book a Call
- Nav gap tightened from 36px to 28px
- Footer links updated to include Services and Full Service Guide

### Added — Client Portal Enhancements (`client.html`)

**System Connections (Data Upload page)**
- Dynamic system connections replacing static list
- `SYSTEMS_LIBRARY`: 19 systems across 5 categories (Finance, Fleet & Transport, Manufacturing ERPs, Productivity, Custom)
- `activeSystems` state array — only connected/pending systems shown
- Add system via categorised picker modal, remove system with confirmation
- "Request a system" form with success message
- Demo state: Sage 200, Webfleet, BigChange (pending), Google Sheets

**Services Upsell (Dashboard page)**
- Six add-on cards at the bottom of the dashboard: Supplier Scorecard, Carbon Baseline Report, Cash Flow Visibility, Labour Productivity Report, Board Reporting Pack, Process Efficiency Audit
- `requestAddon()` function triggers a 6-second confirmation message attributed to the account manager

**Other**
- Demo mode via `?demo` URL parameter — bypasses login and loads Whitfield Logistics directly
- `noindex, nofollow` robots meta — prevents client portal from appearing in search results
- Non-blocking Google Fonts loading
- Chart.js loaded with `defer`

### Fixed — Content Integrity

- Removed all fabricated statistics from the marketing site and audit page
- `audit.html` example findings relabelled "Illustrative · [pattern type]" — no fake company names or invented savings figures
- Systems section intro stat blocks (£28k, 47hrs) removed and replaced with honest descriptive copy
- Specific saving claims in system card descriptions softened to describe problem solved, not results achieved

### Fixed — SEO & Performance (`index.html`)

- Full SEO meta suite: title, description, robots, canonical, Open Graph, Twitter Card
- JSON-LD `ProfessionalService` schema added
- Google Fonts loaded non-blocking (preload + media swap + noscript fallback)
- `will-change: transform` on animated hero orbs for GPU layer promotion
- RAF-throttled scroll listener with `{ passive: true }`
- Chart.js loaded with `defer`
- All form labels given `for` attributes with matching input `id` and `autocomplete` hints
- Six `<div onclick>` auto-cards converted to `<a href>` for SEO crawlability
- SVG favicon added (`favicon.svg`) matching brand gradient

---

## [0.1.0] — 2026-03-07

### Initial Release

First complete version of the Backbone AI platform, encompassing the marketing site, client portal, and operational dashboard.

---

### Added — Marketing Site (`index.html`)

**Hero Section**
- Full-screen hero with animated background grid, floating gradient orbs, and entrance animations
- Core value proposition: "See what your operation is actually costing you"
- Three sourced statistics: £4bn admin waste (YouGov), 7.7 weeks/year in low-value tasks (YouGov), 5% manufacturing AI adoption (ONS)
- Animated counter effect on hero statistics when scrolled into view
- Primary CTA: "Book a Free Audit" / Secondary CTA: "See how it works"

**The Problem Section**
- Six data-backed statistic cards with sources attributed
- Narrative reframe: "British manufacturers are flying blind"
- All statistics independently sourced and attributed (ONS, YouGov/SafetyCulture, ResultSense, TechUK, Consultancy.uk)

**What We Do Section**
- Three service pillars repositioned around operational intelligence:
  1. Surface What's Hidden — data connection and pattern surfacing
  2. Automate the Root Causes — AI-powered workflow automation
  3. Paid on Results — outcome-based pricing model
- Hover glow effects on pillar cards

**Investment Case Section**
- ROI calculation example (logistics firm, Scale plan): £3,500/month retainer generating £4,900/month net gain
- Six automation cards with before/after comparisons and monthly saving figures:
  1. Invoice Processing — £2,100/month, pays back in <2 months
  2. Quality Control Reporting — £1,800/month, pays back in <2 months
  3. Route & Schedule Optimisation — £3,800/month, pays back in <1 month
  4. Supplier Intelligence — £1,400/month, pays back in <3 months
  5. Compliance Documentation — £1,600/month, pays back in <2 months
  6. Inventory & Demand Forecasting — £4,200/month, pays back in <1 month
- Link through to live client dashboard demo

**How It Works Section**
- Five-step engagement process with week-by-week timeline
- Client results metrics panel: 12–18 hours/week saved, 60–85% error reduction, 3–8x ROI in 90 days

**Comparison Table**
- Side-by-side comparison: Backbone AI vs typical consultants and agencies
- Six key differentiators: data quality first, outcome-based pricing, ongoing operations, UK compliance, vertical specialisation, skin in the game

**Pricing Section**
- Three tiers: Pilot (£1,500/month), Scale (£3,500/month + 15% performance), Backbone (£6,500/month + 20% performance)
- One-off setup fees: £5,000 / £10,000 / £15,000
- Featured card highlight on Scale tier

**Industries Section**
- Manufacturing and Logistics positioned as current focus (dual sector)
- Ten specific use cases across both sectors
- Coming-soon pipeline: Construction (Q3), Legal (Q3), Healthcare (Q4), Real Estate (Q4), Retail (2027)

**Client Intake Form**
- Seven data capture fields: name, business name, email, phone, sector, company size, software stack
- Two ROI-calculation fields: hours/week on admin, annual turnover
- Free-text: "biggest operational headache" — the most valuable pre-sales intelligence field
- Drag-and-drop file upload with multi-file support, per-file icons, size formatting, individual removal
- Success state animation on form submission

---

### Added — Client Portal (`client.html`)

**Authentication System**
- 9-digit access code input with auto-tab between digits
- Paste support (pastes across all digit fields)
- Enter key submission
- 1.8-second verification animation with spinner
- Animated transition from login to authenticated app
- Three demo client codes pre-loaded
- Logout returns to login screen with cleared state

**Dashboard Page (default)**
- Four animated KPI cards: total cost saved, hours saved, tasks automated, monthly ROI
- Cubic ease-out counter animation on all KPI values
- 6-month dual-axis trend chart (cost saved in £, hours saved) via Chart.js
- Live activity feed: 5 most recent AI actions with timestamps and savings
- Six automation module cards with status indicators
- Click-through modal system: each module expands to show 4 KPIs, monthly savings bar chart, and timestamped activity log
- Escape key and click-outside to close modals
- Operational insights section: 3 AI-generated patterns surfaced from client data

**Data Upload Page**
- Data completeness score with animated progress bar (73% demo state)
- Four collapsible upload categories: Operational Data, Financial & Invoices, Process Documents, Compliance
- Expand/collapse toggle with chevron animation
- Per-file status tags: Processed (green), Processing (blue), Pending (grey)
- "Still required" items highlighted in orange with explanations of why they're needed
- Drag-and-drop upload zones within each category
- Upload sidebar: outstanding items list, security information (AES-256, UK GDPR, ICO), post-upload process explanation

**Project Tracker Page**
- Five-phase project timeline: Onboarding, Data Foundation, AI Build & Go-live, Optimise & Expand, Advanced Intelligence
- Phase status indicators: Complete (green), In Progress (blue), Planned (grey)
- Individual task cards with: status tag, description, completion date or ETA
- Progress bar on in-progress tasks (65% demo state)
- Mini timeline sidebar showing recent events chronologically
- Project overview sidebar: plan, start date, task counts, account manager name
- Action-required callout with direct link to Data Upload page

---

### Added — Dashboard Demo (`dashboard.html`)

- Standalone version of client dashboard for sales demonstrations
- Accessible without login
- Full sidebar navigation, topbar, all five automation modules
- Identical functionality to client portal dashboard tab
- Linked from marketing site Investment Case section

---

### Added — Project Infrastructure

- `README.md` — comprehensive technical and business documentation
- `CHANGELOG.md` — this file
- `package.json` — project metadata, run scripts
- `.gitignore` — OS, editor, environment, and build exclusions
- `docs/ARCHITECTURE.md` — full technical architecture reference
- `docs/CLIENT_PORTAL.md` — client portal feature specification
- `docs/BUSINESS_MODEL.md` — commercial model documentation
- `docs/ROADMAP.md` — product development roadmap

---

### Technical Decisions

| Decision | Rationale |
|---|---|
| No JavaScript framework | Eliminates build complexity, reduces dependencies, maximises portability |
| CSS custom properties | Enables consistent theming and future white-labelling without search/replace |
| Chart.js via CDN | Avoids npm setup for a static project, industry-standard library |
| Single-file pages | Simplifies deployment — pages can be hosted on any static host without a build step |
| Client-side routing | No server required for page navigation, all state managed in JavaScript |
| Python http.server | Available on any development machine with Python installed, zero config |

---

*For unreleased changes, see the `main` branch commit history.*
