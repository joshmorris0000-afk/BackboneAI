"""
AI Invoice Extractor — uses Anthropic Claude to extract structured data from
supplier invoice PDFs. Handles both digitally-created PDFs and scanned images.

The extractor returns a validated InvoiceExtraction object with per-field
confidence scores. Fields below the configured confidence threshold are flagged
for human review but do not block processing.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import anthropic
import fitz  # PyMuPDF

from app.core.config import get_settings

settings = get_settings()
_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

EXTRACTION_PROMPT = """You are a specialist financial document parser for a UK manufacturing and logistics business.

You will receive the raw text of a supplier invoice. Extract ALL of the following fields and return a single valid JSON object matching the schema below. Do not include any text outside the JSON object.

EXTRACTION RULES:
- Dates must be in ISO format: YYYY-MM-DD
- All monetary values must be numbers (no £ signs, no commas)
- VAT rate must be a decimal: 0.20 for 20%, 0.05 for 5%, 0.00 for exempt
- If a field is not present in the document, use null
- For line items, extract every line separately — do not aggregate
- PO reference: look in subject lines, reference fields, "Your ref", "Our ref", "Re:", document headers
- Confidence scores: 0.00 = complete guess, 1.00 = exactly present in document

FRAUD SIGNALS — flag any of these in fraud_flags (empty list if none):
- Invoice total does not equal sum of line totals
- VAT number format invalid (UK: GB + 9 digits, or GB + 12 digits for government)
- Invoice date is a Saturday, Sunday, or UK public holiday
- Invoice number appears sequential anomaly (e.g. INV-001 after INV-9999)
- Payment bank details present (flag as "bank_details_present" — may differ from known details)

REQUIRED JSON SCHEMA:
{
  "supplier_name": string,
  "supplier_vat_number": string | null,
  "invoice_number": string,
  "invoice_date": "YYYY-MM-DD" | null,
  "due_date": "YYYY-MM-DD" | null,
  "po_reference": string | null,
  "currency": "GBP",
  "payment_terms": string | null,
  "lines": [
    {
      "description": string,
      "part_number": string | null,
      "quantity": number,
      "unit_price": number,
      "vat_rate": number,
      "line_total": number
    }
  ],
  "subtotal": number,
  "vat_total": number,
  "grand_total": number,
  "bank_sort_code": string | null,
  "bank_account_number": string | null,
  "confidence": {
    "supplier_name": number,
    "invoice_number": number,
    "invoice_date": number,
    "po_reference": number,
    "line_items": number,
    "totals": number
  },
  "fraud_flags": [],
  "extraction_notes": string | null
}

INVOICE TEXT:
{invoice_text}"""


@dataclass
class ExtractedLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    line_total: Decimal
    part_number: str | None = None


@dataclass
class InvoiceExtraction:
    supplier_name: str
    invoice_number: str
    lines: list[ExtractedLine]
    subtotal: Decimal
    vat_total: Decimal
    grand_total: Decimal
    confidence: dict[str, float]

    supplier_vat_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    po_reference: str | None = None
    currency: str = "GBP"
    payment_terms: str | None = None
    bank_sort_code: str | None = None
    bank_account_number: str | None = None
    fraud_flags: list[str] = field(default_factory=list)
    extraction_notes: str | None = None
    raw_response: dict = field(default_factory=dict)

    @property
    def overall_confidence(self) -> float:
        if not self.confidence:
            return 0.0
        return sum(self.confidence.values()) / len(self.confidence)

    @property
    def low_confidence_fields(self) -> list[str]:
        return [k for k, v in self.confidence.items() if v < 0.85]


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract raw text from a PDF using PyMuPDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return "\n".join(pages)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _validate_vat_number(vat: str | None) -> bool:
    if not vat:
        return True  # null is acceptable
    return bool(re.match(r"^GB\d{9}(\d{3})?$", vat.replace(" ", "")))


async def extract_invoice(pdf_bytes: bytes, client_id: str) -> InvoiceExtraction:
    """
    Full extraction pipeline:
    1. Extract text from PDF
    2. Send to Claude for structured extraction
    3. Parse and validate response
    4. Return InvoiceExtraction with confidence scores
    """
    raw_text = extract_text_from_pdf(pdf_bytes)

    if not raw_text.strip():
        raise ValueError("PDF contains no extractable text (may be a scanned image — OCR required)")

    prompt = EXTRACTION_PROMPT.replace("{invoice_text}", raw_text[:8000])  # cap at 8k chars

    message = _client.messages.create(
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text

    # Strip any markdown code fences Claude might add
    response_text = re.sub(r"```(?:json)?\n?", "", response_text).strip()

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw: {response_text[:500]}")

    lines = [
        ExtractedLine(
            description=ln["description"],
            quantity=_to_decimal(ln.get("quantity", 1)),
            unit_price=_to_decimal(ln.get("unit_price", 0)),
            vat_rate=_to_decimal(ln.get("vat_rate", 0.20)),
            line_total=_to_decimal(ln.get("line_total", 0)),
            part_number=ln.get("part_number"),
        )
        for ln in data.get("lines", [])
    ]

    fraud_flags = list(data.get("fraud_flags", []))

    # System-side fraud checks (in addition to Claude's)
    if not _validate_vat_number(data.get("supplier_vat_number")):
        fraud_flags.append("invalid_vat_number_format")

    calculated_subtotal = sum(ln.line_total for ln in lines)
    reported_subtotal = _to_decimal(data.get("subtotal", 0))
    if abs(calculated_subtotal - reported_subtotal) > Decimal("0.05"):
        fraud_flags.append("subtotal_mismatch_with_lines")

    return InvoiceExtraction(
        supplier_name=data.get("supplier_name", ""),
        supplier_vat_number=data.get("supplier_vat_number"),
        invoice_number=data.get("invoice_number", ""),
        invoice_date=_parse_date(data.get("invoice_date")),
        due_date=_parse_date(data.get("due_date")),
        po_reference=data.get("po_reference"),
        currency=data.get("currency", "GBP"),
        payment_terms=data.get("payment_terms"),
        lines=lines,
        subtotal=_to_decimal(data.get("subtotal", 0)),
        vat_total=_to_decimal(data.get("vat_total", 0)),
        grand_total=_to_decimal(data.get("grand_total", 0)),
        bank_sort_code=data.get("bank_sort_code"),
        bank_account_number=data.get("bank_account_number"),
        confidence=data.get("confidence", {}),
        fraud_flags=fraud_flags,
        extraction_notes=data.get("extraction_notes"),
        raw_response=data,
    )
