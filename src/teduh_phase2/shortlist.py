from __future__ import annotations

import csv
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .config import DEFAULT_REGION, REGION_CONFIGS, Settings
from .normalize import clean_text


SHORTLIST_FIELDS = [
    "source_project_id",
    "region",
    "display_name",
    "parent_group",
    "project_set",
    "manual_launch_date",
    "manual_built_up_min_sqft",
    "manual_built_up_max_sqft",
    "manual_psf_min",
    "manual_psf_max",
    "tracking_notes",
    "active",
    "date_added",
    "origin",
]
AUDIT_FIELDS = [
    "event_timestamp",
    "changed_by",
    "action",
    "source_project_id",
    "project_name",
    "field",
    "previous_value",
    "new_value",
    "origin",
]
AUDITED_FIELD_LABELS = {
    "region": "Region",
    "display_name": "Display name",
    "parent_group": "Parent group",
    "project_set": "Project set",
    "manual_launch_date": "Launch date",
    "manual_built_up_min_sqft": "Built-up minimum",
    "manual_built_up_max_sqft": "Built-up maximum",
    "manual_psf_min": "PSF minimum",
    "manual_psf_max": "PSF maximum",
    "tracking_notes": "Monitoring notes",
    "active": "Active refresh",
}
PROJECT_SETS = ("reporting_set", "comparator_set", "general")
PROJECT_CODE_PATTERN = re.compile(r"^\d+-\d+$")


def shortlist_path(settings: Settings) -> Path:
    return settings.root / "config" / "shortlist.csv"


def audit_log_path(settings: Settings) -> Path:
    return settings.root / "data" / "audit" / "project_changes.csv"


def _is_active(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "active"}


def _optional_positive_decimal(row: dict[str, Any], field: str, project_code: str) -> str:
    raw = row.get(field)
    if raw in (None, ""):
        return ""
    try:
        value = Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field} for {project_code}: {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{field} must be greater than zero for {project_code}")
    return format(value, "f")


def _optional_iso_date(row: dict[str, Any], field: str, project_code: str) -> str:
    raw = str(row.get(field) or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field} for {project_code}: use YYYY-MM-DD") from exc


def normalize_shortlist_row(row: dict[str, Any]) -> dict[str, str]:
    project_code = str(row.get("source_project_id") or "").strip()
    if not PROJECT_CODE_PATTERN.fullmatch(project_code):
        raise ValueError(f"Invalid TEDUH project code: {project_code!r}")
    project_set = str(row.get("project_set") or "general").strip().casefold()
    if project_set not in PROJECT_SETS:
        raise ValueError(f"Invalid project set for {project_code}: {project_set}")
    region = clean_text(row.get("region")) or DEFAULT_REGION
    if region not in REGION_CONFIGS:
        raise ValueError(f"Invalid region for {project_code}: {region}")
    added = str(row.get("date_added") or date.today().isoformat()).strip()
    try:
        date.fromisoformat(added)
    except ValueError as exc:
        raise ValueError(f"Invalid date_added for {project_code}: {added}") from exc
    built_up_min = _optional_positive_decimal(row, "manual_built_up_min_sqft", project_code)
    built_up_max = _optional_positive_decimal(row, "manual_built_up_max_sqft", project_code)
    psf_min = _optional_positive_decimal(row, "manual_psf_min", project_code)
    psf_max = _optional_positive_decimal(row, "manual_psf_max", project_code)
    for label, minimum, maximum in (
        ("manual built-up", built_up_min, built_up_max),
        ("manual PSF", psf_min, psf_max),
    ):
        if bool(minimum) != bool(maximum):
            raise ValueError(f"Both minimum and maximum are required for {label} on {project_code}")
        if minimum and Decimal(minimum) > Decimal(maximum):
            raise ValueError(f"Minimum exceeds maximum for {label} on {project_code}")
    return {
        "source_project_id": project_code,
        "region": region,
        "display_name": clean_text(row.get("display_name")) or "",
        "parent_group": clean_text(row.get("parent_group")) or "",
        "project_set": project_set,
        "manual_launch_date": _optional_iso_date(row, "manual_launch_date", project_code),
        "manual_built_up_min_sqft": built_up_min,
        "manual_built_up_max_sqft": built_up_max,
        "manual_psf_min": psf_min,
        "manual_psf_max": psf_max,
        "tracking_notes": clean_text(row.get("tracking_notes")) or "",
        "active": "Yes" if _is_active(row.get("active", "Yes")) else "No",
        "date_added": added,
        "origin": clean_text(row.get("origin")) or "manual",
    }


def load_shortlist(settings: Settings, *, active_only: bool = False) -> list[dict[str, str]]:
    path = shortlist_path(settings)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [normalize_shortlist_row(dict(row)) for row in csv.DictReader(handle)]
    seen: set[str] = set()
    for row in rows:
        code = row["source_project_id"]
        if code in seen:
            raise ValueError(f"Duplicate TEDUH project code in shortlist: {code}")
        seen.add(code)
    if active_only:
        rows = [row for row in rows if row["active"] == "Yes"]
    return rows


def write_shortlist(settings: Settings, rows: list[dict[str, Any]]) -> Path:
    path = shortlist_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize_shortlist_row(row) for row in rows]
    codes = [row["source_project_id"] for row in normalized]
    if len(codes) != len(set(codes)):
        raise ValueError("Shortlist contains duplicate TEDUH project codes")
    normalized.sort(
        key=lambda row: (row["region"].casefold(), row["display_name"].casefold(), row["source_project_id"])
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHORTLIST_FIELDS)
        writer.writeheader()
        writer.writerows(normalized)
    os.replace(temporary, path)
    return path


def load_audit_log(settings: Settings) -> list[dict[str, str]]:
    path = audit_log_path(settings)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {field: str(row.get(field) or "") for field in AUDIT_FIELDS}
            for row in csv.DictReader(handle)
        ]


def _append_audit_rows(settings: Settings, rows: list[dict[str, Any]]) -> Path:
    path = audit_log_path(settings)
    if not rows:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    combined = load_audit_log(settings)
    combined.extend(
        {field: str(row.get(field) or "") for field in AUDIT_FIELDS}
        for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        writer.writerows(combined)
    os.replace(temporary, path)
    return path


def _audit_events(
    *,
    existing: dict[str, str] | None,
    updated: dict[str, str],
    changed_by: str,
) -> list[dict[str, str]]:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    actor = clean_text(changed_by) or "Unspecified"
    project_code = updated["source_project_id"]
    project_name = updated["display_name"] or (existing or {}).get("display_name", "") or project_code
    common = {
        "event_timestamp": timestamp,
        "changed_by": actor,
        "source_project_id": project_code,
        "project_name": project_name,
        "origin": updated["origin"],
    }
    if existing is None:
        return [
            {
                **common,
                "action": "Project added",
                "field": "",
                "previous_value": "",
                "new_value": "",
            }
        ]
    events: list[dict[str, str]] = []
    for field, label in AUDITED_FIELD_LABELS.items():
        previous = str(existing.get(field) or "")
        current = str(updated.get(field) or "")
        if previous == current:
            continue
        events.append(
            {
                **common,
                "action": "Project edited",
                "field": label,
                "previous_value": previous,
                "new_value": current,
            }
        )
    return events


def upsert_shortlist_project(
    settings: Settings,
    row: dict[str, Any],
    *,
    changed_by: str = "System",
) -> Path:
    normalized = normalize_shortlist_row(row)
    rows = load_shortlist(settings)
    previous: dict[str, str] | None = None
    updated = False
    for index, existing in enumerate(rows):
        if existing["source_project_id"] == normalized["source_project_id"]:
            previous = existing.copy()
            if not row.get("date_added"):
                normalized["date_added"] = existing["date_added"]
            rows[index] = normalized
            updated = True
            break
    if not updated:
        rows.append(normalized)
    path = write_shortlist(settings, rows)
    _append_audit_rows(
        settings,
        _audit_events(existing=previous, updated=normalized, changed_by=changed_by),
    )
    return path


def shortlist_by_code(settings: Settings) -> dict[str, dict[str, str]]:
    return {row["source_project_id"]: row for row in load_shortlist(settings)}
