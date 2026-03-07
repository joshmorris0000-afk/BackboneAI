# Module 01 — 3-Way PO Matching

**Backbone AI Operational Intelligence Suite**
**Status**: Production-ready | **Version**: 1.0.0 | **March 2026**

---

## What This Module Does

Automatically matches every supplier invoice against the corresponding Purchase Order and Goods Receipt Note. Every discrepancy in price, quantity, or supplier is identified, quantified in £, and routed to the correct human for resolution.

**The result**: AP teams stop spending hours cross-referencing documents manually, and the business stops paying invoices that overcharge or claim payment for goods never received.

---

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Anthropic API key

### Install & Run

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env       # fill in your values
alembic upgrade head       # run database migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Run Tests

```bash
cd backend
pytest tests/ -v
```

### Open the Dashboard

Open `frontend/po_matching.html` directly in a browser, or serve via the Python HTTP server:

```bash
cd frontend
python3 -m http.server 3001
# Visit http://localhost:3001/po_matching.html
```

---

## File Structure

```
po-matching/
├── SPEC.md                          # Full technical & commercial specification
├── README.md                        # This file
├── docs/
│   ├── SECURITY.md                  # Security & compliance documentation
│   └── INTEGRATION_GUIDE.md        # ERP setup guide (Sage 200, Xero, SAP B1)
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                  # FastAPI application entry point
│       ├── core/
│       │   ├── config.py            # Settings (Pydantic, env-driven)
│       │   ├── database.py          # Async SQLAlchemy session
│       │   ├── security.py          # JWT, AES-256-GCM, password hashing
│       │   └── encryption.py        # Field-level encryption helpers
│       ├── models/
│       │   ├── documents.py         # PurchaseOrder, GoodsReceiptNote, Invoice
│       │   ├── match.py             # MatchResult, MatchLineResult
│       │   ├── client.py            # Client, ClientConfig, ConnectorCredential
│       │   ├── supplier.py          # Supplier, SupplierAlias
│       │   ├── user.py              # User (with roles + approval limits)
│       │   └── audit_log.py         # Immutable audit trail
│       ├── services/
│       │   ├── ai_extractor.py      # Claude API document extraction
│       │   ├── matcher.py           # 3-way matching engine
│       │   ├── sync_scheduler.py    # Background ERP sync jobs
│       │   ├── audit.py             # Audit log writer
│       │   └── connectors/
│       │       ├── base.py          # Abstract connector + persistent token mgmt
│       │       ├── sage200.py       # Sage 200 Cloud (OAuth 2.0 + on-prem SQL)
│       │       ├── xero.py          # Xero (OAuth 2.0)
│       │       └── email_ingestion.py # IMAP worker (persistent IDLE connection)
│       └── api/
│           ├── auth.py              # Login, refresh, logout
│           ├── deps.py              # Auth dependencies (get_current_user, require_role)
│           ├── documents.py         # Invoice upload + PO/GRN listing
│           ├── matching.py          # Review queue, approve, override, reject
│           └── reports.py           # Financial summaries and exposure reports
├── frontend/
│   └── po_matching.html            # Full review dashboard (standalone HTML)
└── tests/
    └── test_matcher.py             # Unit tests for the matching engine
```

---

## Architecture

### How a Match Happens

```
1. Invoice arrives         Email attachment (IMAP) or manual upload (UI)
         ↓
2. AI Extraction           Claude reads the PDF → structured JSON
                           Per-field confidence scores
                           Fraud signal detection
         ↓
3. Supplier Resolution     VAT number → exact match
                           Canonical name → exact match
                           Alias table → mapped match
                           Fuzzy name → Levenshtein ≥ 85%
         ↓
4. PO Lookup               Direct PO reference → exact lookup
                           Supplier + date window + total proximity → heuristic
         ↓
5. GRN Lookup              PO → linked GRNs → most recent before invoice date
         ↓
6. Line Matching           Each invoice line vs PO line vs GRN line
                           Price variance (£ and %)
                           Quantity variance (invoice qty vs received qty)
         ↓
7. Status Determination    full_match / partial_match / price_discrepancy /
                           qty_discrepancy / supplier_mismatch / no_po_found / no_grn_found
         ↓
8. Routing                 Full match + within limit → auto-approve
                           Discrepancy → review queue
                           Major exception → AP manager alert
```

### ERP Connections

All ERP connections are established **once at client setup** and maintained permanently by the system. No user or operator is ever prompted to re-authenticate during normal operation.

| System | Auth | Token Management |
|---|---|---|
| Sage 200 Cloud | OAuth 2.0 | Refresh token rotated silently on each renewal |
| Xero | OAuth 2.0 | Access token refreshed every 25 min; 60-day offline access |
| IMAP (Email) | App password / OAuth | Persistent IDLE connection; auto-reconnects on drop |

Credentials are encrypted with AES-256-GCM before storage. Keys live in AWS KMS.

### AI Extraction

Uses `claude-sonnet-4-6` (Anthropic) to read invoice PDFs and extract:
- Supplier name, VAT number
- Invoice number, date, due date
- PO reference (including from free-text fields and email subjects)
- All line items: description, part number, quantity, unit price, VAT rate, line total
- Subtotal, VAT, grand total
- Payment terms, bank details

Returns per-field confidence scores. Fields below 0.85 confidence are flagged for human review.

Also detects fraud signals: total inconsistencies, invalid VAT number format, bank detail changes, duplicate invoice numbers.

---

## Configuration

All settings are per-client and adjustable without redeployment:

| Setting | Default | Effect |
|---|---|---|
| `price_tolerance_pct` | 2% | Variances within this auto-approve. Above → review queue. Above 5% → exception. |
| `qty_tolerance_pct` | 0% | Any quantity difference routes to review |
| `auto_approve_limit_gbp` | £5,000 | Full matches above this always go to review queue |
| `auto_approve_requires_full_match` | true | Partial matches never auto-approve |
| `extraction_confidence_threshold` | 0.85 | Low-confidence extractions held for human review |
| `major_discrepancy_threshold_gbp` | £500 | Triggers email alert to AP manager |

---

## Security

- **Data residency**: AWS eu-west-2 (London) — data never leaves the UK
- **Encryption at rest**: AES-256-GCM on all documents and sensitive credentials
- **Encryption in transit**: TLS 1.3 on all connections
- **Audit trail**: immutable append-only log of every action (7-year retention)
- **Access control**: role-based (admin / ap_manager / ap_reviewer / viewer)
- **No Zapier**: all integrations are built and owned by Backbone AI

See `docs/SECURITY.md` for full compliance documentation (UK GDPR, Cyber Essentials, ISO 27001 alignment).

---

## API

Base URL: `https://api.backbone-ai.com/po-matching/v1`

All endpoints require `Authorization: Bearer <JWT>`.

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Login |
| POST | `/auth/refresh` | Silent token refresh |
| POST | `/invoices/upload` | Upload PDF — triggers extraction + matching |
| GET | `/invoices` | List invoices |
| GET | `/matches` | List match results |
| POST | `/matches/{id}/approve` | Approve a match |
| POST | `/matches/{id}/override` | Manual override with audit trail |
| POST | `/matches/{id}/reject` | Reject invoice |
| GET | `/reports/summary` | Monthly performance summary |
| GET | `/reports/exceptions` | All open exceptions with £ exposure |
| GET | `/reports/financial-exposure` | Total £ at risk |

Full spec in `SPEC.md`.

---

## Tests

```bash
pytest tests/test_matcher.py -v
```

Coverage:
- Exact match
- Price within tolerance
- Price over and under tolerance
- Quantity over GRN (paying for undelivered goods)
- Partial invoice
- No PO line match
- Overall status determination (all statuses)
- Auto-approval eligibility (5 block conditions)
- Supplier fuzzy matching

---

*Backbone AI Ltd — Confidential*
*Module version 1.0.0 — March 2026*
