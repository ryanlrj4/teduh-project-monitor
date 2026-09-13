from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from ..presentation import translate_status_terms, translate_teduh_text


REGION_LABELS = {
    "Kuala Lumpur": "KL",
}


def money(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    return f"RM {float(value):,.0f}"


def source_money(value: object) -> str:
    if value in (None, "", "-"):
        return "N/A"
    try:
        return f"RM {float(str(value).replace(',', '').replace('RM', '').strip()):,.0f}"
    except ValueError:
        return "N/A"


def numeric_range(
    minimum: object,
    maximum: object,
    *,
    prefix: str = "",
    suffix: str = "",
    decimals: int = 0,
) -> str:
    if minimum in (None, "") or maximum in (None, "") or pd.isna(minimum) or pd.isna(maximum):
        return "N/A"
    low = float(minimum)
    high = float(maximum)
    formatter = f",.{decimals}f"
    if round(low, decimals) == round(high, decimals):
        return f"{prefix}{format(low, formatter)}{suffix}"
    return f"{prefix}{format(low, formatter)}–{format(high, formatter)}{suffix}"


def whole_number(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    return f"{int(float(value)):,}"


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"


def display_date(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    text = str(value).strip()
    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    return "N/A" if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def display_timestamp(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.strftime("%d %b %Y, %I:%M %p")


def region_label(value: object) -> str:
    text = str(value or "N/A")
    return REGION_LABELS.get(text, text)


def signed_number(
    value: object,
    *,
    decimals: int = 0,
    suffix: str = "",
    zero_label: str | None = None,
) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if zero_label is not None and abs(number) < 1e-9:
        return zero_label
    return f"{number:+,.{decimals}f}{suffix}"


def status_change(previous: object, current_value: object) -> str:
    previous_text = display_text(previous)
    current_text = display_text(current_value)
    return "No change" if previous_text == current_text else f"{previous_text} → {current_text}"


def display_text(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    return translate_teduh_text(
        value,
        english=st.session_state.get("translate_teduh_values", True),
    )


def status_help(value: object) -> str | None:
    if not st.session_state.get("translate_teduh_values", True):
        return None
    raw = str(value or "").strip()
    return raw if raw and display_text(raw) != raw else None


def status_filter_label(value: object) -> str:
    raw = str(value or "").strip()
    translated = display_text(raw)
    return f"{translated} ({raw})" if translated != raw else translated


def display_status_terms(value: object) -> str:
    return translate_status_terms(
        value,
        english=st.session_state.get("translate_teduh_values", True),
    )


def json_rows(value: object) -> list[dict[str, object]]:
    if value in (None, "") or pd.isna(value):
        return []
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def display_duration(value: object) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f} sec"
    minutes, remaining = divmod(int(round(seconds)), 60)
    return f"{minutes} min {remaining:02d} sec"
