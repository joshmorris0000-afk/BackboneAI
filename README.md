# Backbone AI

**Operational intelligence for UK manufacturing and logistics businesses.**

> We connect your data, automate your admin, and surface the operational patterns that are currently costing you money — managed entirely by us, charged on results.

---

## Table of Contents

1. [What This Project Is](#what-this-project-is)
2. [Business Context](#business-context)
3. [Live Application Pages](#live-application-pages)
4. [Technical Stack](#technical-stack)
5. [Project Structure](#project-structure)
6. [Running Locally](#running-locally)
7. [Page-by-Page Breakdown](#page-by-page-breakdown)
8. [Client Portal — Access Codes](#client-portal--access-codes)
9. [Data & Statistics Sources](#data--statistics-sources)
10. [Roadmap](#roadmap)
11. [Contributing](#contributing)

---

## What This Project Is

Backbone AI is a full-stack marketing and client platform built for a B2B operational intelligence business targeting UK manufacturers and logistics firms.

The codebase contains six distinct applications:

| Application | File | Purpose |
|---|---|---|
| Marketing Site | `index.html` | Public-facing website for lead generation |
| Client Portal | `client.html` | Authenticated dashboard for active clients |
| Dashboard Demo | `dashboard.html` | Standalone demo of the client dashboard |
| Admin Panel | `admin.html` | Internal Backbone AI team panel (amber theme) |
| Service Guide | `services.html` | Full breakdown of all service tiers and add-ons |
| Audit Landing | `audit.html` | Free 2-week operations audit application page |
| Sample Report | `sample-report.html` | Print-optimised PDF report opened by the dashboard download button |

All are built as self-contained HTML files with no external backend dependency — making them fast to deploy, easy to demonstrate, and simple to hand off.

---

## Business Context

### The Problem

UK manufacturing and logistics businesses lose an estimated **£4 billion per year** to administrative inefficiency (YouGov / SafetyCulture). Despite this, only **5% of UK manufacturing firms** have adopted any form of AI (ONS, March 2025).

The existing market for AI consulting and automation tools fails these businesses in three ways:

1. **Consultants advise but don't build** — 87% of businesses say consultancies did not ease their AI transformation fatigue (Consultancy.uk)
2. **Platforms are too technical** — self-serve tools like Zapier require expertise that most SMEs don't have
3. **Agencies build and disappear** — 42% of AI projects are abandoned within 12 months (ResultSense, 2025)

### The Solution

Backbone AI operates as a **managed operational intelligence service**:

- We connect a client's data sources (ERP, spreadsheets, delivery records, quality systems)
- We surface patterns they cannot currently see (supplier reliability trends, process bottlenecks, cost leaks)
- We automate the underlying root causes (invoice processing, route optimisation, compliance reporting)
- We run all systems on an ongoing basis — the client sees results in a dashboard, not a slide deck

### Business Model

| Revenue Stream | Detail |
|---|---|
| Setup fee | £5,000 – £15,000 one-off depending on plan |
| Monthly retainer | £1,500 – £6,500 depending on plan |
| Performance share | 10–20% of measurable savings generated |

This aligns Backbone AI's incentives directly with client outcomes.

---

## Live Application Pages

### 1. Marketing Site (`index.html`)

The public-facing website. Contains:

- **Hero** — core value proposition with sourced statistics
- **The Problem** — data-backed case for why operational intelligence matters
- **What We Do** — three service pillars (Surface What's Hidden, Automate Root Causes, Paid on Results)
- **Investment Case** — ROI calculator and six automation cards with before/after comparisons
- **How It Works** — five-step engagement process with timelines
- **Why Backbone AI** — comparison table vs. consultants and agencies
- **Services** — three-category overview: core retainer, billable add-ons, project work
- **Examples** — ten illustrative systems showing how manual work is automated (no fabricated stats)
- **Pricing** — three transparent tiers (Pilot, Scale, Backbone)
- **Industries** — current focus on manufacturing and logistics, roadmap for others
- **Client Intake Form** — captures company info, software stack, admin hours, and file uploads
- **CTA** — free operational audit offer linking to `audit.html`

Nav order matches scroll order: What We Do → How It Works → Services → Examples → Pricing → Client Login → Book a Call

### 2. Client Portal (`client.html`)

The authenticated client-facing platform. Seven internal pages (sidebar nav):

#### Dashboard (default landing page)
- Animated KPI counters: cost saved, hours saved, tasks automated, monthly ROI
- 6-month savings trend chart (dual axis: £ saved and hours saved)
- Live activity feed showing real-time AI actions
- Module grid: one card per active automation, showing key metrics
- Click-through modals: each module expands to show full KPIs, a monthly bar chart, and timestamped activity log
- Operational insights: AI-surfaced patterns the client couldn't previously see
- **Services upsell section** — six add-on cards with one-click request-to-AM functionality

#### Insights
- 8 AI-surfaced insight cards for Whitfield Logistics, covering supplier reliability, invoice patterns, route inefficiencies, stock alerts, and compliance
- Filter bar with four options: All / Warnings / Opportunities / Positives — filters in place with no page reload
- Severity system with colour-coded left borders (orange=warning, blue=opportunity, green=positive)
- Mark-as-actioned button per card with visual fade and locked state

#### Reports
- 6 report cards: March ops (ready), March compliance (ready), Feb supplier scorecard (sent), Feb fleet efficiency (sent), Feb ops report (sent), March supplier scorecard (scheduled)
- Status badges: Ready, Sent, Scheduled
- Preview modal: opens for each report showing 6 key data points (no download required to see summary)
- Download PDF: opens `sample-report.html?print` which triggers the browser's Save as PDF dialog

#### Services
- Six add-on cards: Supplier Scorecard, Carbon Baseline Report, Cash Flow Visibility, Labour Productivity Report, Board Reporting Pack, Process Efficiency Audit
- One-click "Request this →" sends a request to the account manager with a 6-second confirmation

#### Automation Detail Pages (Invoice Processing, Route Optimisation, Supplier Intel, Compliance Docs, Inventory Forecast)
- Shared template (`page-automation`) loaded dynamically via `loadAutoPage(key)`
- Each page shows: 4 KPI cards, 6-month savings bar chart, live activity log
- Enriched detail section below the chart, specific to each module:
  - **Invoice Processing** — 10-row recent invoices table (Invoice #, Supplier, Amount, PO Match, Status, Time Saved) + 3 stat cards (avg 2.3 min processing, 3 duplicates blocked, 100% error recovery)
  - **Route Optimisation** — 10-row weekly routes table (Vehicle, Route, Original/Optimised Miles, Saving, Status) + 3 stat cards (94% on-time, 447 miles saved, 20 vehicles)
  - **Supplier Intelligence** — 14-supplier scorecard table (On-Time %, Invoice Accuracy, Trend, Status) with Midlands Freight at 72% flagged At Risk + 3 active alert cards
  - **Compliance Docs** — 8-document library table with download buttons and status badges + 3 upcoming auto-draft entries
  - **Inventory Forecast** — 12-SKU Stock Watch table with colour-coded days remaining (red <7, orange 7–14, green 14+) + 3 stat cards

#### Data Upload
- Data completeness score (percentage + progress bar)
- Four categorised upload sections: Operational Data, Financial & Invoices, Process Documents, Compliance
- Dynamic system connections with 19-system library, add/remove/request flow
- Drag-and-drop upload zones with file type validation
- Security information (AES-256 encryption, UK GDPR compliance, ICO framework)

#### Project Tracker
- Five-phase project timeline from Onboarding through to Advanced Intelligence
- Each phase contains individual tasks with: status, description, completion date or ETA, and progress bars for in-progress work
- Sidebar: project overview stats, mini timeline of recent events, action-required callout

### 3. Dashboard Demo (`dashboard.html`)

A standalone version of the client dashboard for sales demonstrations. Does not require login. Used in the marketing site's "Investment Case" section as a live link.

All sidebar navigation items are fully built out:

- **Dashboard** — KPI counters, 6-month trend chart, activity feed, module cards with modals
- **Insights** — AI-surfaced operational findings with severity badges, filterable by type, mark-as-actioned
- **Reports** — report cards with inline preview modal; "Download PDF" opens `sample-report.html` which auto-triggers the browser Save as PDF dialog
- **Settings** — editable account form, notification toggles, portal access code reveal, data export request
- **Automation detail pages** — each module card links to a dedicated page showing KPIs, a monthly bar chart, and timestamped activity log

The date range selector in the topbar (30 / 60 / 90 / 180 / 365 days) updates the trend chart labels and data live.

---

## Technical Stack

This project is intentionally built with zero framework dependencies for maximum simplicity, performance, and portability.

| Layer | Technology | Reason |
|---|---|---|
| Markup | HTML5 | Semantic, accessible, no compilation required |
| Styling | CSS3 (custom properties, grid, flexbox) | Full control, no build step, no class-name conflicts |
| Interactivity | Vanilla JavaScript (ES6+) | No framework overhead, runs anywhere |
| Charts | Chart.js v4.4.0 (CDN) | Industry-standard, lightweight, no npm install required |
| Typography | Inter (Google Fonts) | Clean, professional, widely readable |
| Icons | Unicode emoji + inline SVG | No icon library dependency |
| Server (local) | Python 3 `http.server` | Available on any machine with Python installed |

### Design System

The entire visual language is defined through CSS custom properties in `:root`:

```css
--bg:      #05050a   /* Primary background — near black */
--bg2:     #0c0c14   /* Secondary background — dark navy */
--surface: rgba(255,255,255,0.04)  /* Card surfaces */
--border:  rgba(255,255,255,0.08)  /* All borders */
--blue:    #3b82f6   /* Primary brand colour */
--cyan:    #06b6d4   /* Accent colour */
--green:   #22c55e   /* Positive / savings */
--orange:  #f97316   /* Warning / alerts */
--red:     #f43f5e   /* Errors / negative */
--purple:  #8b5cf6   /* Secondary accent */
--text:    #f1f5f9   /* Primary text */
--muted:   #64748b   /* Muted/secondary text */
--muted2:  #94a3b8   /* Mid-level muted text */
```

Changing any of these variables instantly updates the entire application's colour scheme.

---

## Project Structure

```
backbone-ai/
│
├── index.html              # Public marketing website
├── client.html             # Client portal (login + 3-page app)
├── dashboard.html          # Standalone dashboard demo
├── admin.html              # Internal admin panel (amber theme, team-only)
├── services.html           # Full service guide — all tiers and add-ons
├── audit.html              # Free operations audit application page
├── sample-report.html      # Print-optimised PDF report (opened by dashboard download button)
├── favicon.svg             # Brand SVG favicon (blue→cyan gradient)
│
├── docs/
│   ├── ARCHITECTURE.md     # Full technical architecture reference
│   ├── CLIENT_PORTAL.md    # Client portal feature specification
│   ├── BUSINESS_MODEL.md   # Commercial model and pricing logic
│   └── ROADMAP.md          # Product development roadmap
│
├── README.md               # This file — primary project documentation
├── CHANGELOG.md            # Version history and release notes
├── package.json            # Project metadata and run scripts
└── .gitignore              # Files excluded from version control
```

---

## Running Locally

### Option 1 — Python (recommended, no install required)

```bash
cd path/to/backbone-ai
python3 -m http.server 3000
```

Then open: [http://localhost:3000](http://localhost:3000)

### Option 2 — Node serve

```bash
npx serve . -p 3000
```

### Option 3 — Open directly in browser

```
file:///path/to/backbone-ai/index.html
```

Note: some browser security policies block local file requests when opened directly. The Python server method is recommended.

---

## Page-by-Page Breakdown

### Marketing Site — Key JavaScript Features

#### Scroll Reveal Animation
All content sections use an `IntersectionObserver` to animate elements into view as the user scrolls:

```javascript
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.12 });
```

Elements start with `opacity: 0; transform: translateY(32px)` and transition to `opacity: 1; transform: translateY(0)` when they enter the viewport. Stagger delays (`reveal-delay-1`, `reveal-delay-2`, `reveal-delay-3`) create a cascade effect on grouped elements.

#### Hero Stat Counters
The three hero statistics animate from 0 to their target values using a cubic ease-out function when they scroll into view:

```javascript
function animateCounter(el, target, suffix, prefix) {
  const eased = 1 - Math.pow(1 - progress, 3); // cubic ease-out
  el.textContent = prefix + value + suffix;
}
```

#### File Upload (Intake Form)
The client intake form supports drag-and-drop and click-to-browse file uploads with:
- Multi-file selection
- Per-file icon assignment based on extension
- File size formatting (B / KB / MB)
- Individual file removal
- Animated file list entries on add

#### Form Success State
On submission, the form fields fade out and a success confirmation fades in — all handled with CSS class toggling, no page reload.

---

### Client Portal — Key Architecture

#### Authentication Model
The portal uses a 9-digit access code system. In the current version, client codes and their associated data are stored in a JavaScript object for demonstration purposes:

```javascript
const CLIENTS = {
  '123456789': { name: 'Whitfield Logistics Ltd', sector: 'Logistics & Distribution', plan: 'Scale' },
  '987654321': { name: 'Thornton Manufacturing Co', sector: 'Manufacturing', plan: 'Backbone' },
  '456123789': { name: 'Northern Freight Solutions', sector: 'Logistics & Distribution', plan: 'Pilot' },
};
```

**In production**, this would be replaced with a server-side API call:
- Code submitted via `POST /api/auth/verify`
- Server validates against database, returns JWT token
- Token stored in `sessionStorage`, sent with all subsequent API requests
- Dashboard data fetched from `GET /api/client/dashboard` using the token

#### Page Routing
The portal uses client-side routing — a single HTML file with multiple "pages" toggled by CSS class:

```javascript
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
}
```

No page reload occurs when navigating between Dashboard, Data Upload, and Project Tracker.

#### Chart.js Integration
Two chart types are used:
- **Line chart** (dashboard trend): dual-axis, showing £ saved and hours saved over 6 months
- **Bar chart** (module modals): monthly savings per automation, colour-coded to the module

All charts are responsive, use the project's colour palette, and have custom tick formatters (`£` prefix, `h` suffix).

#### Module Modal System
Each automation module card opens a modal containing:
1. Four KPI tiles specific to that automation
2. A 6-month bar chart of monthly savings
3. A timestamped activity log of recent AI actions

The modal is a single DOM element with content injected via JavaScript on open. This means only one modal instance exists in the DOM regardless of how many modules are visible.

---

## Client Portal — Access Codes

For demonstration purposes, three client codes are pre-loaded:

| Code | Client | Sector | Plan |
|---|---|---|---|
| `123-456-789` | Whitfield Logistics Ltd | Logistics & Distribution | Scale |
| `987-654-321` | Thornton Manufacturing Co | Manufacturing | Backbone |
| `456-123-789` | Northern Freight Solutions | Logistics & Distribution | Pilot |

---

## Data & Statistics Sources

All statistics displayed on the marketing site are sourced from independent research. The following table maps each statistic to its origin:

| Statistic | Source | URL |
|---|---|---|
| £4bn lost annually to admin waste in UK manufacturing | YouGov / SafetyCulture | [The Manufacturer](https://www.themanufacturer.com/articles/uk-manufacturers-losing-4bn-a-year-to-wasted-managers-time-finds-yougov/) |
| 7.7 weeks/year managers spend on low-value tasks | YouGov / SafetyCulture | [The Manufacturer](https://www.themanufacturer.com/articles/uk-manufacturers-losing-4bn-a-year-to-wasted-managers-time-finds-yougov/) |
| 5% of UK manufacturing firms use AI | Office for National Statistics | [ONS, March 2025](https://www.ons.gov.uk/economy/economicoutputandproductivity/productivitymeasures/articles/managementpracticesandtheadoptionoftechnologyandartificialintelligenceinukfirms2023/2025-03-24) |
| 42% of UK AI projects scrapped | ResultSense | [ResultSense, Oct 2025](https://www.resultsense.com/insights/2025-10-21-uk-businesses-scrapping-ai-initiatives-how-to-avoid-failure) |
| 95% of AI failures caused by data quality issues | ResultSense | [ResultSense, Nov 2025](https://www.resultsense.com/insights/2025-11-04-data-readiness-ai-implementation-five-step-framework) |
| 87% of businesses say consultancies worsened fatigue | Consultancy.uk | [Consultancy.uk, 2025](https://www.consultancy.uk/news/41589/consultancies-at-risk-of-contributing-to-ai-change-fatigue) |
| 46% of AI pilots never reach production | ResultSense | [ResultSense, Oct 2025](https://www.resultsense.com/insights/2025-10-27-banking-precision-revolution-ai-strategy) |
| 68% cite skills shortage as primary AI blocker | TechUK | [TechUK, 2025](https://www.techuk.org/resource/major-barriers-to-ai-adoption-remain-for-uk-businesses-despite-growing-demand-new-report-reveals.html) |

---

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full product roadmap.

### Near-term (Q2 2026)
- [ ] Backend API (FastAPI + PostgreSQL) to replace demo data
- [ ] Real authentication (JWT + secure session management)
- [ ] File upload connected to cloud storage (AWS S3 / UK region)
- [x] Admin panel for the Backbone AI team to manage clients (`admin.html`)
- [x] Services page and audit landing page

### Medium-term (Q3 2026)
- [ ] Real-time data connections (ERP integrations: Sage, SAP, Xero)
- [ ] Automated reporting emails (weekly/monthly summary to client)
- [ ] Proprietary sector benchmarking database
- [ ] Construction vertical launch

### Long-term (2027)
- [ ] Fine-tuned AI model for UK manufacturing and logistics
- [ ] Predictive maintenance module
- [ ] Customer-facing delivery intelligence (B2B2C)
- [ ] Mobile app for site managers and logistics controllers

---

## Contributing

This is a private commercial codebase. All contributions require prior approval from the project owner.

**Code style conventions:**
- HTML: semantic elements, meaningful class names, no inline styles except dynamic values
- CSS: custom properties for all colours, mobile-first responsive design
- JavaScript: ES6+, no frameworks, clear function names, comments on non-obvious logic

---

*Built by Backbone AI Ltd. Registered in England & Wales.*
*Last updated: March 2026 — v0.3.6*
