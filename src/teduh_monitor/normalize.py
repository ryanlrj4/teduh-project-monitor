from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .config import HIMS_UNIT_DATA_START_ISO


MISSING_TEXT = {"", "-", "n/a", "na", "null", "none", "tiada maklumat"}


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in MISSING_TEXT:
        return None
    return re.sub(r"\s+", " ", text)


def parse_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = clean_text(value)
    if text is None:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", ".", "-", "-."}:
        return None
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -parsed if negative and parsed > 0 else parsed


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if text is None:
        return None
    candidates = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
    )
    for pattern in candidates:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return None


def safe_percentage(numerator: int | Decimal, denominator: int | Decimal | None) -> float | None:
    if denominator in (None, 0):
        return None
    return round(float(Decimal(numerator) / Decimal(denominator) * 100), 6)


def normalized_status_token(value: Any) -> str:
    text = clean_text(value) or ""
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


SOLD = {"dijual", "telah dijual", "sold"}
UNSOLD = {"belum dijual", "avail", "available", "unsold"}
BOOKED = {"tempahan", "booked", "booking", "ditempah"}
RESERVED = {"reserved", "reservation", "rizab"}


def normalize_sales_status(status_jualan: Any, availability_status: Any = None) -> str:
    primary = normalized_status_token(status_jualan)
    fallback = normalized_status_token(availability_status)
    for token in (primary, fallback):
        if token in SOLD:
            return "sold"
        if token in UNSOLD:
            return "unsold"
        if token in BOOKED:
            return "booked"
        if token in RESERVED:
            return "reserved"
    return "unknown"


def normalize_state(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    canonical = {
        "wp kuala lumpur": "Wp Kuala Lumpur",
        "pulau pinang": "Pulau Pinang",
        "selangor": "Selangor",
        "johor": "Johor",
        "melaka": "Melaka",
    }
    return canonical.get(text.casefold(), text)


def iso_or_none(value: Any) -> str | None:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def hims_project_reference(
    first_spa_value: Any, permit_start_value: Any
) -> tuple[str | None, str | None]:
    """Choose the project-age proxy used for the HIMS coverage cutoff.

    A first PJB/SPA date identifies an older project even when its advertising
    permit was renewed after HIMS began. Projects without a first PJB/SPA date
    (commonly not-started projects) fall back to the permit start date.
    """
    first_spa_date = iso_or_none(first_spa_value)
    if first_spa_date:
        return first_spa_date, "first_spa_date"
    permit_start_date = iso_or_none(permit_start_value)
    if permit_start_date:
        return permit_start_date, "permit_start_date_fallback"
    return None, None


def is_hims_eligible(first_spa_value: Any, permit_start_value: Any) -> bool:
    reference_date, _ = hims_project_reference(first_spa_value, permit_start_value)
    return reference_date is not None and reference_date >= HIMS_UNIT_DATA_START_ISO
