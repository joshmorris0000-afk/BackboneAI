# Architecture Reference

## Overview

Backbone AI is currently a **static web application** — three HTML files with embedded CSS and JavaScript, served by any HTTP server. There is no backend, no database, and no build process in v0.1.0.

This is an intentional architectural decision for the current phase: it allows rapid iteration, zero deployment friction, and easy demonstration to clients without infrastructure dependencies.

The architecture is designed to evolve cleanly into a full-stack application in v0.2.0 without requiring a rewrite of the frontend.

---

## Current Architecture (v0.1.0)

```
┌─────────────────────────────────────────┐
│              Client Browser             │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │index.html│  │client.html│  │dash.. │ │
│  │  (site)  │  │ (portal) │  │ .html │ │
│  └──────────┘  └──────────┘  └───────┘ │
│       │              │                  │
│  CSS + JS       CSS + JS + Chart.js     │
│  (embedded)     (embedded)              │
└─────────────────────────────────────────┘
          │
          ▼
  ┌───────────────┐
  │  HTTP Server  │
  │  (Python 3 /  │
  │  any static)  │
  └───────────────┘
```

All logic — authentication, page routing, data rendering, charts — runs in the browser. No network requests are made to any backend service.

---

## Planned Architecture (v0.2.0)

The v0.2.0 backend will be built with FastAPI (Python) — consistent with the other Backbone AI projects in this repository owner's portfolio (Neural Connections, PharmaU). This keeps the entire stack in Python and allows shared infrastructure.

```
┌─────────────────────────────────────────────────────┐
│                   Client Browser                    │
│                                                     │
│  index.html       client.html        dashboard.html │
│  (marketing)      (portal SPA)       (demo)         │
│       │                │                            │
│       │         fetch() API calls                   │
└───────┼────────────────┼────────────────────────────┘
        │                │
        ▼                ▼
┌───────────────────────────────────────────┐
│              FastAPI Backend              │
│                                           │
│  POST /api/auth/verify    (login)         │
│  GET  /api/client/dashboard              │
│  GET  /api/client/modules/:id            │
│  POST /api/client/upload                 │
│  GET  /api/client/tracker                │
│                                           │
│  JWT middleware on all /api/client/* routes│
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────┐    ┌─────────────────┐
│   PostgreSQL DB   │    │   AWS S3 (UK)   │
│                   │    │                 │
│  clients          │    │  Uploaded files │
│  automations      │    │  (AES-256)      │
│  savings_log      │    │                 │
│  activity_feed    │    │                 │
│  project_tasks    │    │                 │
│  uploaded_files   │    │                 │
└───────────────────┘    └─────────────────┘
```

---

## File Responsibilities

### `index.html` — Marketing Site

**Responsibility:** Public-facing lead generation and brand communication.

**Contains:**
- All CSS for the marketing site (embedded in `<style>` tag)
- All page sections as semantic HTML
- Scroll reveal system (`IntersectionObserver`)
- Hero counter animation
- File upload handler (intake form)
- Form success state

**External dependencies:**
- Google Fonts (Inter) — loaded via `<link>`
- No JavaScript libraries

**Key JavaScript functions:**
```
animateCounter(el, target, suffix, prefix)  — animates stat numbers
fadeUp animations                           — CSS keyframe, no JS needed
IntersectionObserver                        — scroll reveal trigger
File upload handler                         — drag/drop + input handling
Form submit handler                         — success state toggle
```

---

### `client.html` — Client Portal

**Responsibility:** Authenticated client-facing operational intelligence platform.

**Contains:**
- Login screen (9-digit code input, verification animation, error states)
- Full authenticated app shell (sidebar, topbar, page content area)
- Three page views: Dashboard, Data Upload, Project Tracker
- Module modal system
- All Chart.js chart definitions

**External dependencies:**
- Google Fonts (Inter) — `<link>`
- Chart.js v4.4.0 — CDN `<script>`

**Key JavaScript objects:**
```javascript
CLIENTS {}          — demo client data, maps code → client profile
MODULES {}          — demo module data, maps key → KPIs, chart data, activity log
```

**Key JavaScript functions:**
```
attemptLogin()      — validates code, triggers transition to app
logout()            — clears state, returns to login
showPage(id, btn)   — switches active page, updates nav and topbar
animCount(el, ...)  — KPI counter animation
initCharts()        — initialises Chart.js instances
openModal(key)      — injects module data and opens modal
closeModal()        — removes open class
toggleCat(id)       — expand/collapse upload categories
```

**State model:**
```
authenticated: bool     — whether login has succeeded
currentPage: string     — 'dashboard' | 'upload' | 'tracker'
trendChart: Chart       — Chart.js instance reference (prevent re-init)
modalChartInst: Chart   — Modal chart instance (destroyed on each open)
```

---

### `dashboard.html` — Demo Dashboard

**Responsibility:** Standalone sales demonstration, does not require login.

**Contains:** Identical dashboard UI to `client.html`, minus the login screen and upload/tracker pages.

**Note:** In v0.2.0, this file will be deprecated and replaced by a demo mode flag on `client.html`.

---

## Authentication Architecture

### Current (v0.1.0) — Client-side only

```
User enters code
      │
      ▼
getCode() — concatenates 9 digit inputs
      │
      ▼
CLIENTS[code] — object lookup
      │
  ┌───┴───┐
found?     not found?
  │              │
load app    show error
```

**Limitations:**
- All valid codes are visible in the browser's JavaScript source
- No session persistence (refresh returns to login)
- No rate limiting on code attempts

### Production (v0.2.0) — Server-side

```
User enters code
      │
      ▼
POST /api/auth/verify { code: "123456789" }
      │
      ▼
Server: bcrypt.compare(code, stored_hash)
      │
  ┌───┴────┐
 valid?    invalid?
   │            │
JWT token   HTTP 401
stored in   + attempt log
sessionStorage
   │
fetch('/api/client/dashboard', {
  headers: { Authorization: `Bearer ${token}` }
})
```

---

## Routing Architecture

### Current — CSS class toggling

```javascript
// Show page
document.getElementById('page-' + id).classList.add('active');

// CSS
.page { display: none; }
.page.active { display: block; }
```

No URL changes occur when navigating. Refresh always returns to the default (Dashboard) page.

### Production — Hash routing (v0.2.0)

```javascript
// URLs: /client#dashboard, /client#upload, /client#tracker
window.location.hash = '#' + id;

window.addEventListener('hashchange', () => {
  showPage(location.hash.slice(1));
});
```

This allows bookmarking, browser back/forward navigation, and shareable deep links.

---

## Data Flow (Current)

```
Static data object in JS
    │
    ▼
DOM injection via innerHTML
    │
    ▼
Chart.js renders canvas element
    │
    ▼
User sees dashboard
```

## Data Flow (Production)

```
Client authenticates → receives JWT
    │
    ▼
GET /api/client/dashboard (JWT in header)
    │
    ▼
Server queries PostgreSQL savings_log, activity_feed, automations
    │
    ▼
JSON response → client renders dashboard
    │
    ▼
WebSocket connection for live activity feed updates
```

---

## Security Considerations

### Current (v0.1.0)
- No sensitive data is stored or transmitted
- All data is demo/illustrative
- HTTPS not required for local development

### Production Requirements
- All traffic over HTTPS (TLS 1.3)
- JWT tokens: RS256 algorithm, 8-hour expiry, refresh token rotation
- File uploads: server-side virus scanning before storage
- AES-256 encryption for all stored files
- Rate limiting: 5 failed login attempts → 15 minute lockout
- All data stored in UK AWS region (eu-west-2) for GDPR compliance
- ICO registration required before processing any client data

---

## Performance Characteristics

| Metric | Current (v0.1.0) | Target (v0.2.0) |
|---|---|---|
| Initial page load | <200ms (local) | <1.5s (production, CDN) |
| Time to interactive | <300ms | <2s |
| Dashboard render | <100ms (no API) | <500ms (with API) |
| Chart render | ~50ms | ~50ms |
| Bundle size | 0 (no bundler) | <150KB gzipped |

---

*Document version: 1.0 — March 2026*
