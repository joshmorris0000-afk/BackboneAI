# 3-Way Purchase Order Matching — Technical & Commercial Specification

**Module**: `po-matching`
**Owner**: Backbone AI Ltd
**Version**: 1.0.0
**Status**: Production-ready
**Last updated**: March 2026

---

## 1. Overview

### 1.1 What This Module Does

3-Way PO Matching is the automated process of reconciling three financial documents for every supplier transaction:

| Document | Source | Contains |
|---|---|---|
| **Purchase Order (PO)** | Client ERP / procurement system | Supplier, line items ordered, agreed unit prices, delivery dates |
| **Goods Receipt Note (GRN)** | Client ERP / warehouse system | What was actually received, in what quantities, on what date |
| **Supplier Invoice** | Supplier (PDF via email or upload) | What the supplier is claiming payment for |

A transaction **passes** matching when all three documents agree within configured tolerances. A transaction **fails** when discrepancies exist — and those discrepancies are quantified, categorised, and routed to the correct human for resolution.

### 1.2 The Problem This Solves

Without automated 3-way matching, UK manufacturing and logistics businesses:

- Pay invoices that overcharge on agreed unit prices (supplier price drift)
- Pay invoices for quantities never received (short deliveries, damaged goods)
- Miss credit note opportunities (overpayments already made)
- Spend 2–6 hours per week of skilled AP time on manual cross-referencing
- Discover discrepancies only at year-end audit, when recovery is near-impossible

### 1.3 Deployment Model

This module is deployed by Backbone AI on behalf of a client as part of their managed service. The client does not install or operate the system — they access a review dashboard showing results. All ingestion, processing, and matching runs automatically.

---

## 2. Data Model

### 2.1 Purchase Order

```
PurchaseOrder
├── id                  UUID (primary key)
├── client_id           UUID (FK → clients)
├── po_number           String (unique per client)
├── supplier_id         UUID (FK → suppliers)
├── supplier_name       String
├── issued_date         Date
├── expected_delivery   Date
├── currency            String (default: GBP)
├── status              Enum: draft | issued | partially_received | fully_received | cancelled
├── source              Enum: sage200 | xero | sap_b1 | manual | csv_import
├── source_ref          String (ERP internal ID)
├── created_at          Timestamp
├── updated_at          Timestamp
└── lines[]
    ├── id              UUID
    ├── line_number     Integer
    ├── description     String
    ├── part_number     String (nullable)
    ├── quantity        Decimal(12,4)
    ├── unit_price      Decimal(12,4)
    ├── vat_rate        Decimal(5,4) (e.g. 0.20 for 20%)
    ├── uom             String (each, kg, litre, metre…)
    └── line_total      Decimal(12,4) (quantity × unit_price)
```

### 2.2 Goods Receipt Note

```
GoodsReceiptNote
├── id                  UUID
├── client_id           UUID
├── grn_number          String (unique per client)
├── po_id               UUID (FK → purchase_orders, nullable — may arrive before PO linked)
├── supplier_id         UUID
├── received_date       Date
├── received_by         String (warehouse operative name)
├── source              Enum: sage200 | xero | sap_b1 | manual | csv_import
├── source_ref          String
├── notes               Text
├── created_at          Timestamp
└── lines[]
    ├── id              UUID
    ├── po_line_id      UUID (FK → po lines, nullable)
    ├── description     String
    ├── part_number     String (nullable)
    ├── quantity_ordered    Decimal(12,4)
    ├── quantity_received   Decimal(12,4)
    ├── quantity_rejected   Decimal(12,4) (damaged / failed QC)
    ├── rejection_reason    String (nullable)
    └── uom             String
```

### 2.3 Invoice

```
Invoice
├── id                  UUID
├── client_id           UUID
├── invoice_number      String
├── supplier_id         UUID (resolved by AI extraction + lookup)
├── supplier_name_raw   String (as extracted from document)
├── invoice_date        Date
├── due_date            Date (nullable)
├── po_reference_raw    String (as extracted — may be imprecise)
├── currency            String
├── subtotal            Decimal(12,4)
├── vat_total           Decimal(12,4)
├── grand_total         Decimal(12,4)
├── payment_terms       String (nullable)
├── source              Enum: email | upload | api
├── raw_file_path       String (encrypted S3 key)
├── extraction_confidence   Decimal(5,4) (0.00–1.00, from AI)
├── extraction_model    String (model used for extraction)
├── status              Enum: pending_extraction | extracted | matched | exception | approved | paid
├── created_at          Timestamp
└── lines[]
    ├── id              UUID
    ├── description     String
    ├── quantity        Decimal(12,4)
    ├── unit_price      Decimal(12,4)
    ├── vat_rate        Decimal(5,4)
    ├── line_total      Decimal(12,4)
    └── po_line_ref     String (nullable — as stated on invoice)
```

### 2.4 Match Result

```
MatchResult
├── id                  UUID
├── client_id           UUID
├── invoice_id          UUID (FK)
├── po_id               UUID (FK, nullable)
├── grn_id              UUID (FK, nullable)
├── status              Enum: full_match | partial_match | price_discrepancy | qty_discrepancy | supplier_mismatch | no_po_found | no_grn_found | manual_override
├── match_score         Decimal(5,4) (0.00–1.00, overall confidence)
├── matched_at          Timestamp
├── matched_by          Enum: auto | manual
├── reviewer_id         UUID (nullable — if manual)
├── approved_at         Timestamp (nullable)
├── approved_by         UUID (nullable)
├── exception_reason    Text (nullable)
├── discrepancy_total   Decimal(12,4) (£ value of total discrepancy)
└── line_results[]
    ├── id              UUID
    ├── invoice_line_id UUID
    ├── po_line_id      UUID (nullable)
    ├── grn_line_id     UUID (nullable)
    ├── status          Enum: matched | price_over | price_under | qty_over | qty_under | not_on_po | not_received
    ├── po_unit_price   Decimal(12,4)
    ├── invoice_unit_price  Decimal(12,4)
    ├── price_variance  Decimal(12,4) (invoice − PO, £)
    ├── price_variance_pct  Decimal(7,4) (%)
    ├── po_quantity     Decimal(12,4)
    ├── grn_quantity    Decimal(12,4)
    ├── invoice_quantity    Decimal(12,4)
    ├── qty_variance    Decimal(12,4)
    └── financial_exposure  Decimal(12,4) (£ at risk on this line)
```

### 2.5 Audit Log

Every state change, every user action, every automated decision is written to an immutable audit log:

```
AuditLog
├── id              UUID
├── client_id       UUID
├── entity_type     String (invoice | po | grn | match_result)
├── entity_id       UUID
├── action          String (created | updated | matched | approved | exception_raised | override | exported)
├── actor_type      Enum: system | user
├── actor_id        UUID (nullable — system actions have no user)
├── actor_ip        String (hashed)
├── before_state    JSONB (nullable)
├── after_state     JSONB
├── notes           Text (nullable)
└── created_at      Timestamp (immutable — never updated)
```

---

## 3. Matching Engine

### 3.1 Matching Sequence

```
Invoice arrives (email / upload)
        │
        ▼
[1] AI Extraction
    Claude parses PDF → structured JSON
    Confidence score assigned per field
        │
        ▼
[2] Supplier Resolution
    Match supplier_name_raw → known suppliers table
    Fuzzy match + manual mapping fallback
        │
        ▼
[3] PO Lookup
    Search by: PO reference on invoice → supplier → date range
    Ranked candidates returned
        │
        ▼
[4] GRN Lookup
    Find GRNs linked to matched PO
    Filter by date ≤ invoice date
        │
        ▼
[5] Line-Level Matching
    Each invoice line matched against PO lines + GRN lines
    Status assigned per line
        │
        ▼
[6] Overall Status Determination
    Aggregate line statuses → match result status
        │
        ▼
[7] Routing
    full_match     → auto-approve queue (or direct approval if configured)
    partial_match  → reviewer queue (AP team)
    exception      → exception queue (AP manager)
```

### 3.2 Matching Rules

#### Supplier Match
| Rule | Logic |
|---|---|
| Exact name | `invoice_supplier == po_supplier` (case-insensitive) |
| Fuzzy name | Levenshtein similarity ≥ 85% |
| Mapped alias | Supplier alias table (e.g. "ABC Ltd" = "ABC Trading Limited") |
| VAT number | If both documents carry VAT numbers, exact match takes priority |

#### PO Reference Match
| Rule | Logic |
|---|---|
| Direct reference | Invoice carries PO number → exact lookup |
| Extracted reference | AI extracts PO number from free text (e.g. "Re: Purchase Order PO-2026-0441") |
| Heuristic lookup | No PO ref → search by supplier + approximate total + date window (±30 days) |

#### Price Matching (per line)
| Variance | Status | Action |
|---|---|---|
| 0% | `matched` | Auto-approve eligible |
| > 0% and ≤ 2% | `matched` (within tolerance) | Auto-approve eligible |
| > 2% and ≤ 5% | `price_discrepancy` (minor) | Reviewer queue |
| > 5% | `price_discrepancy` (major) | Exception queue + immediate alert |

*Tolerances are configurable per client.*

#### Quantity Matching (per line)
| Scenario | Status | Action |
|---|---|---|
| Invoice qty = GRN received qty | `matched` | Auto-approve eligible |
| Invoice qty = PO qty but GRN qty < PO qty | `qty_discrepancy` | Hold — goods not fully received |
| Invoice qty < GRN qty | `matched` (partial invoice — acceptable) | Reviewer queue |
| Invoice qty > GRN qty | `qty_over` | Exception — paying for undelivered goods |

#### Overall Match Status
| Condition | Overall Status |
|---|---|
| All lines matched (within tolerance) | `full_match` |
| ≥ 1 line price_discrepancy (minor), no qty issues | `partial_match` |
| Any line `qty_over` | `qty_discrepancy` |
| Any line `price_discrepancy` (major) | `price_discrepancy` |
| No PO found | `no_po_found` |
| No GRN found | `no_grn_found` |
| Supplier mismatch | `supplier_mismatch` |

### 3.3 Auto-Approval Rules

Auto-approval (no human required) is permitted only when ALL of the following are true:
- Match status is `full_match`
- All price variances ≤ configured tolerance (default 2%)
- All quantities within tolerance
- Invoice total ≤ client auto-approval limit (configurable, default £5,000)
- Supplier is on approved supplier list
- Invoice not flagged by fraud detection rules

Auto-approval limit and tolerance thresholds are set per client in `ClientConfig`.

---

## 4. AI Extraction

### 4.1 Model

**Primary**: `claude-sonnet-4-6` (Anthropic)
**Fallback**: Rule-based regex extraction (for simple structured invoices)

### 4.2 Extraction Process

1. PDF received → PyMuPDF extracts raw text + layout
2. Raw text sent to Claude with structured extraction prompt
3. Claude returns JSON matching the `InvoiceExtraction` schema
4. Per-field confidence scores returned
5. Low-confidence fields flagged for human review (threshold: < 0.85)

### 4.3 Extraction Schema (Claude output)

```json
{
  "supplier_name": "Midlands Steel Supplies Ltd",
  "supplier_vat_number": "GB123456789",
  "invoice_number": "INV-2026-04412",
  "invoice_date": "2026-03-05",
  "due_date": "2026-04-04",
  "po_reference": "PO-2026-0441",
  "currency": "GBP",
  "payment_terms": "30 days net",
  "lines": [
    {
      "description": "Mild Steel Sheet 3mm 2500x1250mm",
      "part_number": "MS-SHEET-3MM",
      "quantity": 20.0,
      "unit_price": 48.50,
      "vat_rate": 0.20,
      "line_total": 970.00
    }
  ],
  "subtotal": 970.00,
  "vat_total": 194.00,
  "grand_total": 1164.00,
  "confidence": {
    "supplier_name": 0.98,
    "invoice_number": 0.99,
    "invoice_date": 0.97,
    "po_reference": 0.82,
    "line_items": 0.94,
    "totals": 0.99
  },
  "extraction_notes": "PO reference found in email subject line, not on invoice body"
}
```

### 4.4 Fraud Detection Signals

Claude also evaluates the following during extraction and flags anomalies:

- Invoice number follows a non-sequential pattern vs. prior invoices from same supplier
- Invoice date is a weekend or public holiday (unusual for UK manufacturing)
- Bank account details differ from previous invoices (potential mandate fraud)
- Grand total inconsistent with line item sum
- VAT number does not match HMRC format (GB + 9 digits)
- Duplicate invoice number already in system

---

## 5. ERP Integrations

All integrations are built and maintained by Backbone AI. No third-party middleware.

### 5.1 Supported Systems (v1.0)

| System | Integration Type | Data Pulled |
|---|---|---|
| Sage 200 Cloud | REST API (OAuth 2.0) | POs, GRNs, Suppliers |
| Xero | REST API (OAuth 2.0) | POs, Bills (as invoices), Contacts |
| SAP Business One | Service Layer REST API | POs, GRNs, Business Partners |
| Manual / CSV | File upload | POs and GRNs from any source |
| Email (IMAP) | Direct IMAP connection | Supplier invoices (PDF attachments) |

### 5.2 Sync Frequency

| Data Type | Frequency |
|---|---|
| Purchase Orders | Every 15 minutes |
| Goods Receipts | Every 15 minutes |
| Suppliers | Every 60 minutes |
| Email inbox scan | Every 5 minutes |

### 5.3 Sage 200 Cloud Connector

- Auth: OAuth 2.0 with refresh token rotation
- Endpoints used: `/purchaseOrders`, `/purchaseOrderLines`, `/goodsReceived`, `/suppliers`
- Rate limit: 600 requests/minute (handled with exponential backoff)
- On-premise Sage 200: SQL Server direct connection (read-only service account)

### 5.4 Xero Connector

- Auth: OAuth 2.0, 30-minute token refresh
- Endpoints: `/PurchaseOrders`, `/Bills` (supplier invoices), `/Contacts`
- Webhook support: Xero pushes PO updates in real time (supplementing polling)

### 5.5 Email Ingestion

- Protocol: IMAP with IDLE support (push notification of new emails)
- Supports: Gmail, Microsoft 365, generic IMAP (any provider)
- Filters: configured sender whitelist, subject line patterns, attachment type (PDF only)
- Security: TLS on all IMAP connections, credentials stored encrypted

---

## 6. API Specification

Base URL: `https://api.backbone-ai.com/po-matching/v1`

All endpoints require `Authorization: Bearer <JWT>` header.

### 6.1 Authentication

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Obtain JWT (username + password) |
| POST | `/auth/refresh` | Refresh JWT using refresh token |
| POST | `/auth/logout` | Invalidate session |

### 6.2 Documents

| Method | Path | Description |
|---|---|---|
| GET | `/invoices` | List invoices (filterable by status, date, supplier) |
| GET | `/invoices/{id}` | Get invoice + extracted data |
| POST | `/invoices/upload` | Upload invoice PDF manually |
| GET | `/purchase-orders` | List POs |
| GET | `/purchase-orders/{id}` | Get PO with lines |
| GET | `/grns` | List GRNs |
| GET | `/grns/{id}` | Get GRN with lines |

### 6.3 Matching

| Method | Path | Description |
|---|---|---|
| GET | `/matches` | List match results (filterable) |
| GET | `/matches/{id}` | Get full match detail |
| POST | `/matches/{id}/approve` | Approve a match (reviewer action) |
| POST | `/matches/{id}/override` | Override with manual resolution + reason |
| POST | `/matches/{id}/reject` | Reject invoice (raise dispute) |
| POST | `/matches/run` | Trigger matching run for a specific invoice |

### 6.4 Configuration

| Method | Path | Description |
|---|---|---|
| GET | `/config` | Get client matching configuration |
| PATCH | `/config` | Update tolerances, auto-approve limits |
| GET | `/suppliers` | List known suppliers + aliases |
| POST | `/suppliers/{id}/alias` | Add supplier name alias |

### 6.5 Reports

| Method | Path | Description |
|---|---|---|
| GET | `/reports/summary` | Monthly summary: volumes, match rates, £ discrepancies found |
| GET | `/reports/exceptions` | All unresolved exceptions |
| GET | `/reports/financial-exposure` | Total £ at risk across open discrepancies |
| GET | `/reports/supplier/{id}` | Per-supplier match history and discrepancy trends |

---

## 7. User Roles & Permissions

| Role | Can Do |
|---|---|
| `admin` | All actions, configuration changes, user management |
| `ap_manager` | Approve/reject all matches, override, view all reports, configure tolerances |
| `ap_reviewer` | Approve matches below their approval limit, raise exceptions, view assigned queue |
| `viewer` | Read-only: view matches, reports |
| `system` | Internal: automated matching, ingestion (no human login) |

---

## 8. Performance Targets

| Metric | Target |
|---|---|
| Email → extraction complete | < 90 seconds |
| Extraction → match result | < 30 seconds |
| End-to-end (email in → match result) | < 3 minutes |
| Auto-approval (full match, no review) | < 5 minutes total |
| UI dashboard load | < 1.5 seconds |
| API response time (p95) | < 400ms |
| System availability | 99.9% uptime |

---

## 9. Deployment Architecture

```
Internet
    │
    ▼
[Cloudflare] — DDoS protection, WAF, TLS termination
    │
    ▼
[AWS ALB] — Load balancer (eu-west-2, London)
    │
    ├── [FastAPI App] × 2 (ECS Fargate, auto-scaling)
    │
    ├── [PostgreSQL] — RDS (Multi-AZ, eu-west-2)
    │
    ├── [Redis] — ElastiCache (session store, rate limiting, job queue)
    │
    ├── [S3] — Raw document storage (server-side AES-256, eu-west-2)
    │
    └── [SES / IMAP Worker] — Email ingestion service (ECS Fargate)
```

All infrastructure in AWS eu-west-2 (London). No data leaves the UK.

---

## 10. Failure Handling

| Failure | Behaviour |
|---|---|
| AI extraction fails | Retry × 3, then route to manual extraction queue |
| ERP sync fails | Log error, retry on next cycle, alert Backbone AI ops team |
| Low confidence extraction | Flag fields for human review, do not auto-approve |
| Duplicate invoice detected | Block processing, alert AP team immediately |
| ERP unavailable | Queue documents, process when ERP recovers |
| Match ambiguous (multiple POs match) | Route to reviewer with all candidates ranked |

---

## 11. Client Configuration (per deployment)

```python
ClientConfig:
    price_tolerance_pct: float = 0.02       # 2% default
    qty_tolerance_pct: float = 0.00         # 0% default (exact qty)
    auto_approve_enabled: bool = True
    auto_approve_limit_gbp: float = 5000.0
    auto_approve_requires_full_match: bool = True
    extraction_confidence_threshold: float = 0.85
    email_addresses: list[str]              # supplier invoice inboxes
    erp_system: str                         # sage200 | xero | sap_b1
    currency: str = "GBP"
    vat_registered: bool = True
    payment_terms_default: int = 30         # days
    alert_email: str                        # AP manager alert address
    alert_on_major_discrepancy: bool = True
    major_discrepancy_threshold_gbp: float = 500.0
```

---

*Backbone AI Ltd — Confidential. This document is for internal and client use only.*
*Specification version 1.0.0 — March 2026*
