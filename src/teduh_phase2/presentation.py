from __future__ import annotations

import re
from typing import Any

import pandas as pd


ALERT_PRESENTATION = {
    "status_sakit": ("Sakit status", "Status exception", "Critical"),
    "permit_cancelled": ("Cancelled status", "Status exception", "Critical"),
    "status_lewat": ("Lewat status", "Status exception", "High"),
    "status_changed": ("TEDUH status changed", "Status change", "Review"),
    "sold_units_decreased": ("Reported sold units decreased", "Source revision", "Review"),
    "construction_decreased": ("Reported construction decreased", "Source revision", "Review"),
    "construction_unavailable": ("Construction unavailable", "Data quality", "Notice"),
    "completion_certificate_obtained": ("CCC/CFO evidence reported", "Completion", "Notice"),
}

TEDUH_ENGLISH_LABELS = {
    "aktif": "Active",
    "tidak aktif": "Inactive",
    "berfasa": "Phased development",
    "jadual g": "Schedule G",
    "jadual h": "Schedule H",
    "ya": "Yes",
    "tidak": "No",
    "pangsapuri servis": "Serviced apartment",
    "pangsapuri suite": "Apartment suite",
    "rumah pangsa/kondo": "Flat/condominium",
    "rumah teres": "Terraced house",
    "daerah barat daya, pulau pinang": "Southwest District, Penang",
    "daerah timor laut, pulau pinang": "Northeast District, Penang",
    "kuala lumpur, wp kuala lumpur": "Kuala Lumpur, Federal Territory of Kuala Lumpur",
    "wp kuala lumpur": "Federal Territory of Kuala Lumpur",
}


def translate_teduh_text(value: object, *, english: bool) -> str:
    """Translate selected TEDUH display values without modifying stored source data."""
    text = str(value)
    if not english:
        return text
    translated = TEDUH_ENGLISH_LABELS.get(text.strip().casefold())
    if translated:
        return translated
    period = re.fullmatch(r"(\d+(?:\.\d+)?)\s+bulan", text.strip(), flags=re.IGNORECASE)
    if period:
        amount = period.group(1)
        unit = "month" if amount in {"1", "1.0"} else "months"
        return f"{amount} {unit}"
    return text


def _changed(previous: object, current: object) -> bool:
    previous_missing = previous is None or pd.isna(previous)
    current_missing = current is None or pd.isna(current)
    if previous_missing or current_missing:
        return previous_missing != current_missing
    if isinstance(previous, (int, float)) or isinstance(current, (int, float)):
        try:
            return abs(float(current) - float(previous)) > 1e-9
        except (TypeError, ValueError):
            pass
    return str(previous) != str(current)


def latest_project_changes(current: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Return projects whose latest snapshot differs from their prior dated observation."""
    columns = [
        "source_project_id",
        "display_name",
        "region",
        "previous_snapshot_date",
        "current_snapshot_date",
        "previous_status",
        "current_status",
        "sold_units_delta",
        "sales_percentage_delta",
        "construction_percentage_delta",
    ]
    if current.empty or history.empty:
        return pd.DataFrame(columns=columns)

    prepared_history = history.copy()
    prepared_history["source_project_id"] = prepared_history["source_project_id"].astype(str)
    prepared_history["_observation_date"] = pd.to_datetime(
        prepared_history["snapshot_date"], errors="coerce"
    )
    prepared_history = prepared_history.dropna(subset=["_observation_date"])
    if "retrieved_at" not in prepared_history.columns:
        prepared_history["retrieved_at"] = ""

    changes: list[dict[str, Any]] = []
    for _, current_row in current.iterrows():
        project_code = str(current_row.get("source_project_id") or "")
        current_date = pd.to_datetime(current_row.get("snapshot_date"), errors="coerce")
        if not project_code or pd.isna(current_date):
            continue
        earlier = prepared_history[
            (prepared_history["source_project_id"] == project_code)
            & (prepared_history["_observation_date"] < current_date)
        ].sort_values(["_observation_date", "retrieved_at"], na_position="first")
        if earlier.empty:
            continue
        previous = earlier.iloc[-1]

        tracked_fields = (
            "project_status",
            "sold_units",
            "sales_percentage",
            "construction_percentage",
        )
        if not any(_changed(previous.get(field), current_row.get(field)) for field in tracked_fields):
            continue

        def delta(field: str) -> float | None:
            previous_value = previous.get(field)
            current_value = current_row.get(field)
            if previous_value is None or current_value is None:
                return None
            if pd.isna(previous_value) or pd.isna(current_value):
                return None
            return float(current_value) - float(previous_value)

        changes.append(
            {
                "source_project_id": project_code,
                "display_name": current_row.get("display_name")
                or current_row.get("project_name")
                or project_code,
                "region": current_row.get("region"),
                "previous_snapshot_date": previous.get("snapshot_date"),
                "current_snapshot_date": current_row.get("snapshot_date"),
                "previous_status": previous.get("project_status"),
                "current_status": current_row.get("project_status"),
                "sold_units_delta": delta("sold_units"),
                "sales_percentage_delta": delta("sales_percentage"),
                "construction_percentage_delta": delta("construction_percentage"),
            }
        )
    return pd.DataFrame(changes, columns=columns)


def present_alert(row: dict[str, Any]) -> dict[str, Any]:
    """Add concise, business-facing labels without changing the stored alert record."""
    code = str(row.get("alert_code") or "")
    label, category, level = ALERT_PRESENTATION.get(
        code,
        (code.replace("_", " ").strip().title() or "Monitoring alert", "Monitoring", "Review"),
    )
    return {
        **row,
        "alert_label": label,
        "alert_category": category,
        "alert_level": level,
    }
