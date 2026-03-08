"""
Statement parser — extracts structured line items from raw supplier statement text.

Supports:
- Free-text/PDF extraction via Claude (handles any layout)
- Structured CSV import

For PDF upload, the caller first extracts text with PyMuPDF then passes it here.
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import anthropic

from app.core.config import get_settings

settings = get_settings()
_ai = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


EXTRACTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["supplier_reference", "transaction_date", "amount", "transaction_type"],
        "properties": {
            "supplier_reference": {"type": "string"},
            "our_reference": {"type": "string"},
            "transaction_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            "due_date": {"type": "string", "description": "ISO date YYYY-MM-DD or null"},
            "amount": {"type": "number", "description": "Positive for invoices, negative for credits/payments"},
            "description": {"type": "string"},
            "transaction_type": {"type": "string", "enum": ["invoice", "credit_note", "payment"]},
        },
    },
}


async def extract_statement_lines_from_text(raw_text: str) -> list[dict[str, Any]]:
    """
    Use Claude to extract structured statement line items from raw statement text.
    Returns a list of dicts matching the line item schema.
    """
    prompt = f"""You are a data extraction assistant. Extract all transaction line items from this supplier statement.

For each line extract:
- supplier_reference: the supplier's own invoice/credit note reference number
- our_reference: our purchase order or invoice reference if shown (may be null)
- transaction_date: date of the transaction (ISO format YYYY-MM-DD)
- due_date: payment due date if shown (ISO format or null)
- amount: numeric amount. Positive for invoices/charges, negative for credits/payments.
- description: brief description if provided
- transaction_type: "invoice", "credit_note", or "payment"

Return ONLY a valid JSON array. No explanation. No markdown.

STATEMENT TEXT:
{raw_text}"""

    message = await _ai.messages.create(
        model=settings.ai_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    return json.loads(raw)


def parse_statement_line(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and coerce a raw extracted line into our internal format.
    Raises ValueError if required fields are missing or malformed.
    """
    ref = raw.get("supplier_reference", "").strip()
    if not ref:
        raise ValueError("supplier_reference is required")

    try:
        txn_date = date.fromisoformat(raw["transaction_date"])
    except (KeyError, ValueError):
        raise ValueError(f"Invalid transaction_date: {raw.get('transaction_date')}")

    try:
        amount = Decimal(str(raw["amount"]))
    except (KeyError, InvalidOperation):
        raise ValueError(f"Invalid amount: {raw.get('amount')}")

    due_raw = raw.get("due_date")
    try:
        due_date = date.fromisoformat(due_raw) if due_raw else None
    except ValueError:
        due_date = None

    txn_type = raw.get("transaction_type", "invoice")
    if txn_type not in ("invoice", "credit_note", "payment"):
        txn_type = "invoice"

    return {
        "supplier_reference": ref,
        "our_reference": raw.get("our_reference"),
        "transaction_date": txn_date,
        "due_date": due_date,
        "amount": amount,
        "description": raw.get("description"),
        "transaction_type": txn_type,
    }
