# Client Portal — Feature Specification

## Overview

The client portal (`client.html`) is a single-page application delivered to active Backbone AI clients. It gives clients full transparency into the AI systems running inside their business — what's being automated, how much it's saving them, what data we need, and what work is in progress.

The portal has three distinct functional areas, accessible from the sidebar navigation after authentication.

---

## Authentication

### 9-Digit Access Code System

Each client is issued a unique 9-digit numeric code upon contract signing. This code is their sole credential for portal access.

**UX design rationale:** 9 digits avoids email/password complexity (no forgotten password flows, no email verification), while being long enough to resist brute-force attempts in a production environment. The visual grouping (XXX–XXX–XXX) matches familiar number formats (phone numbers, bank sort codes) and reduces input errors.

**Input behaviour:**
- Each digit occupies a separate input field
- Focus automatically advances to the next field on input
- Backspace on an empty field moves focus back to the previous field
- Full paste support: pasting `123456789` populates all 9 fields
- Enter key triggers login submission
- All inputs are `inputmode="numeric"` for correct mobile keyboard display

**Verification flow:**
1. Code submitted → 1.8-second artificial delay with spinner (simulates server call)
2. Valid code → fade out login screen, fade in app shell
3. Invalid code → error message, fields cleared, focus returned to first digit

**Demo codes for testing:**

| Code | Client | Plan |
|---|---|---|
| 123-456-789 | Whitfield Logistics Ltd | Scale |
| 987-654-321 | Thornton Manufacturing Co | Backbone |
| 456-123-789 | Northern Freight Solutions | Pilot |

---

## Page 1 — Dashboard (Default Landing Page)

The dashboard is the first page a client sees after logging in. It answers the question: **"What has the AI done for my business this month?"**

### KPI Cards

Four top-level metrics displayed in animated cards that count up from zero on load:

| KPI | What it shows |
|---|---|
| Cost Saved This Month | Total £ value of savings generated across all automations |
| Hours Saved | Staff hours reclaimed by AI automation this month |
| Tasks Automated | Total number of individual items processed (invoices, routes, reports, etc.) |
| Monthly ROI | Ratio of savings to retainer cost (e.g. 3.7x = saving £3.70 for every £1 paid) |

Each card has a colour-coded accent (green = financial, blue = operational, orange = volume, purple = ROI) and shows month-on-month change.

### 6-Month Trend Chart

A dual-axis line chart showing the growth of Backbone AI's impact over time:
- **Left axis (green):** Monthly cost savings in £
- **Right axis (blue):** Monthly hours saved

The chart demonstrates the compounding nature of the service — as more automations go live and systems are refined, savings grow month-on-month. This is the most important chart for client retention conversations.

### Live Activity Feed

A real-time (simulated in v0.1.0) feed of recent AI actions. Shows the last 5 events with:
- Colour-coded dot (green = positive, orange = alert, red = error caught)
- Human-readable description of what happened
- Timestamp
- Value of the action (time saved, £ saved, error caught)

This feed answers: "What exactly is the AI doing?" — the most common early-stage client question.

### Automation Module Cards

One card per active automation. Each card shows:
- Module name and sector
- Status indicator (Live / In Setup)
- Four key metrics specific to that automation type
- Monthly saving figure
- "View detail →" prompt

**Click interaction:** Opens a modal with:
- Four expanded KPI tiles
- Monthly savings bar chart (last 6 months)
- Timestamped activity log (last 5 events)
- Escape key or click-outside closes the modal

### Operational Insights

Three AI-generated insights surfaced from the client's data. Each insight:
- Identifies a pattern the client couldn't see before
- Quantifies the cost or opportunity
- Suggests a specific action

This section is the clearest demonstration of the "operational intelligence" positioning — it's not just automation, it's understanding.

---

## Page 2 — Data Upload

The data upload page serves two purposes:
1. Collect the documents Backbone AI needs to build and improve the AI systems
2. Give clients visibility into what has been received and what is still outstanding

### Completeness Score

A percentage score (0–100%) showing how complete the client's data submission is. Calculated as:

```
completeness = (items_received / items_required) × 100
```

Displayed with an animated progress bar. Low completeness scores are a prompt to action — the client can see that incomplete data means incomplete AI capability.

### Upload Categories

Four collapsible sections, each representing a type of data:

**1. Operational Data**
ERP exports, production logs, delivery records, shift schedules. Used to: train route optimisation, build production reports, understand operational patterns.

**2. Financial & Invoice Data**
Sample supplier invoices, purchase orders, statements. Used to: train invoice processing AI, set anomaly detection thresholds, establish supplier benchmarks.

**3. Process Documents**
Standard operating procedures, driver handbooks, quality checklists, workflow diagrams. Used to: understand the client's current processes before automating them. We automate what they actually do, not what we assume they do.

**4. Compliance & Regulatory**
Operator licences, insurance certificates, ISO records, HSE assessments. Used to: ensure compliance documentation automation outputs are correctly formatted for their regulatory requirements.

### File Status Indicators

Each previously uploaded file shows one of three states:
- **Processed** (green) — received, cleaned, integrated into the AI systems
- **Processing** (blue) — received, being worked on by the Backbone AI team
- **Pending** (grey) — awaiting upload

### Required Items

Items still needed are highlighted in orange within each category, with an explanation of why they're required. This prevents the common "why do you need this?" support conversation.

### Upload Interface

Within each category: a drag-and-drop zone with a hidden `<input type="file">`. Supports:
- Multiple file selection
- Drag-and-drop from file manager
- All common document types (PDF, Excel, CSV, Word, images)

### Security Information

Prominently displayed in the sidebar:
- AES-256 encryption in transit and at rest
- UK-based servers only
- UK GDPR and ICO compliance
- Files deleted on request

This directly addresses the most common objection to sharing operational data.

---

## Page 3 — Project Tracker

The project tracker gives clients full visibility into the engagement — what has been completed, what is in progress, and what is planned. It eliminates the "what are you actually doing?" question.

### Phase Structure

The engagement is divided into five phases:

| Phase | Name | Typical Duration |
|---|---|---|
| 1 | Onboarding & Discovery | 1 week |
| 2 | Data Foundation | 2 weeks |
| 3 | AI System Build & Go-live | 3 weeks |
| 4 | Optimise & Expand | Ongoing |
| 5 | Advanced Intelligence Layer | Q2 onwards |

Each phase displays as a collapsible card with:
- Phase number and colour-coded status indicator
- Status badge: Complete / In Progress / Planned
- Individual task list

### Task Cards

Each task shows:
- Status icon (✓ complete, ⚙ in progress, ○ planned)
- Task name and description
- Completion date (for done tasks) or ETA (for planned tasks)
- Status tag
- Progress bar (for in-progress tasks showing % completion)

### Sidebar

**Project Overview:** Key stats at a glance — plan, start date, tasks complete vs total, tasks in progress, planned, account manager name.

**Recent Updates Timeline:** A mini chronological feed of the most recent project events, giving a quick sense of momentum.

**Action Required Callout:** If there is a blocking item (e.g. an outstanding data upload preventing a build), this callout appears in the sidebar with a direct link to the relevant page. This makes blockers unavoidable and actionable.

---

## Navigation

The sidebar provides persistent navigation between all three pages. Each navigation item:
- Highlights when its page is active
- Shows a badge for actionable items (e.g. "2 needed" on Data Upload when items are outstanding)

The topbar updates its title and subtitle to reflect the current page context.

---

## Responsive Design

The portal is designed for desktop-first use (1200px+ optimal), with responsive breakpoints at:
- 1100px: two-column layouts collapse to single column
- Module grid collapses from 3 columns to 2 columns
- Modal KPI grid collapses from 4 to 2 columns

Mobile use is supported but not the primary use case — clients typically access the portal from a desktop during business hours.

---

## Production Upgrade Path

When the backend is built (v0.2.0), the following changes will be made to `client.html`:

| Current (v0.1.0) | Production (v0.2.0) |
|---|---|
| `CLIENTS {}` object | `POST /api/auth/verify` API call |
| `MODULES {}` static data | `GET /api/client/modules` API call |
| No session persistence | JWT in `sessionStorage`, refresh restores session |
| Static file list | `GET /api/client/files` — live upload status |
| Static task list | `GET /api/client/tracker` — live task states |
| No real file upload | `POST /api/client/upload` — S3 multipart upload |
| Simulated activity feed | WebSocket: `wss://api.backboneai.co.uk/ws/activity` |

The HTML structure, CSS, and chart implementations remain unchanged between v0.1.0 and v0.2.0. Only the data layer changes.

---

*Document version: 1.0 — March 2026*
