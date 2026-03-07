# Module 02 — Supplier Price Drift Detector

**Backbone AI Operational Intelligence Suite**
**Status**: Production-ready | **Version**: 1.0.0 | **March 2026**

---

## What This Module Does

Monitors every invoice line item against contracted supplier prices and surfaces drift before it becomes material. Instead of discovering at year-end that a supplier has been charging 8% above contract for 11 months, the system raises an alert on the first invoice where drift is detected — with an AI-generated plain English summary telling the AP manager exactly what to do.

**The result**: price creep is caught within days, not months. Recovery is possible. Disputes are raised before payment. Suppliers know their pricing is under active monitoring.

---

## The Problem It Solves

Manual price verification against contracts is either:
- Not done at all (no time, too many line items)
- Done at annual contract review, by which point tens of thousands in overpayments have accumulated
- Done inconsistently — high-value items checked, low-value items waved through

This system checks every line, on every invoice, automatically.

---

## Severity Levels

| Level | Threshold | Action |
|---|---|---|
| **Info** | < 2% | Logged silently — no alert |
| **Warning** | 2–5% | Added to review queue |
| **Alert** | 5–10% | AP manager notified, formal review required |
| **Critical** | > 10% | Immediate email alert, escalation to AP manager |

All thresholds are configurable per client and per contracted price.

---

## Quick Start

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --port 8001
```

Open `frontend/price_drift.html` in a browser.

---

## File Structure

```
supplier-price-drift/
├── README.md
├── backend/
│   └── app/
│       ├── core/
│       │   ├── config.py          # Settings with drift thresholds
│       │   └── database.py        # Async SQLAlchemy
│       ├── models/
│       │   └── price_data.py      # ContractedPrice, PriceObservation,
│       │                          #   DriftAlert, SupplierPriceTrend
│       ├── services/
│       │   └── drift_detector.py  # Core detection engine + AI summaries
│       └── api/
│           └── drift.py           # REST endpoints
└── tests/
    └── test_drift_detector.py    # 20 unit tests
└── frontend/
    └── price_drift.html          # Full monitoring dashboard
```

---

## How It Works

### 1. Contracted Prices
Load the agreed price for each SKU/product from each supplier. Can be entered manually via the UI or imported from a CSV. Each contracted price has:
- Optional SKU for exact matching
- Description for fuzzy matching
- Valid date range
- Optional per-SKU tolerance override

### 2. Invoice Line Processing
When an invoice is processed (by Module 01 or manually uploaded), every line is passed to the drift detector:

```python
results = await process_invoice_lines(db, lines, client_tolerance=Decimal("0.02"))
```

### 3. Matching Logic
Priority order for finding the contracted price:
1. SKU exact match (if SKU provided on invoice line)
2. Description fuzzy match (≥ 80% similarity via RapidFuzz token_set_ratio)

If no contracted price is found, the observation is still recorded — but flagged as "unmatched" for later manual association.

### 4. Drift Calculation

```
variance = observed_unit_price - contracted_unit_price
variance_pct = (variance / contracted_unit_price) × 100
financial_impact = variance × quantity_invoiced
```

### 5. Alert Generation
If `abs(variance_pct) > tolerance`:
- A `DriftAlert` record is created
- Claude generates a plain-English summary (2–3 sentences, written for an AP manager)
- Alert is added to the open queue
- Email sent if severity ≥ configured notification threshold

### 6. Alert Lifecycle
```
open → acknowledged → resolved
  └──────────────→ disputed
```
All transitions logged in the audit trail.

---

## AI Summaries

Every alert above warning level gets an AI-generated summary written for the AP manager:

> *Midlands Steel Supplies invoiced steel sheet at £54.20/unit against a contracted rate of £48.50 — a 11.75% overcharge. This has cost £114.00 on this invoice alone, with £1,840 in drift identified over the past 90 days. Recommend raising a formal price dispute and requesting a credit note.*

No interpretation needed. The manager reads one sentence and knows what to do.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/price-drift/contracted-prices` | Add a contracted price |
| GET | `/price-drift/contracted-prices` | List contracted prices |
| GET | `/price-drift/alerts` | List alerts (filterable by status, severity, supplier) |
| GET | `/price-drift/alerts/{id}` | Full alert detail with observation data |
| POST | `/price-drift/alerts/{id}/resolve` | Resolve/dispute an alert |
| GET | `/price-drift/summary` | Overall drift summary for a period |

---

## Data Model

```
ContractedPrice     — agreed price per SKU/product per supplier
PriceObservation    — every invoice line checked, with drift calculated
DriftAlert          — raised when drift exceeds threshold; AI summary attached
SupplierPriceTrend  — monthly rollup by supplier (nightly aggregation)
```

---

## Tests

```bash
pytest tests/test_drift_detector.py -v
```

**20 tests covering:**
- Severity level calculation at each threshold boundary
- Negative variance (price decreases)
- Financial impact arithmetic (positive and negative)
- Drift direction assignment
- Tolerance logic (within / just over / custom tight / custom loose)
- Monthly accumulation (including credit offsets)
- Description normalisation for fuzzy matching

---

## Integration with Other Modules

This module runs automatically when Module 01 (3-Way PO Matching) processes invoices. The PO Matching system passes invoice lines to the drift detector as part of the same pipeline.

It can also run standalone: pass any invoice line programmatically via `process_invoice_lines()`.

---

*Backbone AI Ltd — Confidential*
*Module version 1.0.0 — March 2026*
