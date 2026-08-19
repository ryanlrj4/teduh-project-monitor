from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import duckdb

from .config import REGION_CONFIGS, Settings
from .export import FIELD_SPECS, FIELDS
from .metrics import calculate_project_metrics
from .normalize import is_hims_eligible, normalize_state
from .sources import SourceAnomaly, TeduhClient
from .validate import require_no_errors, validate_records
from .shortlist import load_shortlist


Progress = Callable[[str], None]
ProjectProgress = Callable[[int, int], None]
MANUAL_FIELD_SPECS: list[tuple[str, str]] = [
    ("region", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("parent_group", "VARCHAR"),
    ("project_set", "VARCHAR"),
    ("manual_launch_date", "DATE"),
    ("manual_built_up_min_sqft", "DECIMAL(16,2)"),
    ("manual_built_up_max_sqft", "DECIMAL(16,2)"),
    ("manual_psf_min", "DECIMAL(16,2)"),
    ("manual_psf_max", "DECIMAL(16,2)"),
    ("priority", "VARCHAR"),
    ("tracking_notes", "VARCHAR"),
    ("shortlist_active", "VARCHAR"),
    ("shortlist_origin", "VARCHAR"),
    ("project_scale_band", "VARCHAR"),
    ("commercial_scope", "VARCHAR"),
    ("commercial_scope_reason", "VARCHAR"),
]
SHORTLIST_FIELD_SPECS = MANUAL_FIELD_SPECS + FIELD_SPECS
SHORTLIST_FIELDS = [name for name, _ in SHORTLIST_FIELD_SPECS]
ALERT_FIELDS = [
    "snapshot_date",
    "region",
    "severity",
    "alert_code",
    "source_project_id",
    "display_name",
    "message",
]
VALIDATION_CODES = [
    ("active_data_rich", "30031-1"),
    ("active_mid_sales", "30513-1"),
    ("risk_status", "4131-139"),
    ("completed_ccc", "19760-2"),
    ("manual_name_parent_mapping", "31096-1"),
]


def current_metrics_path(settings: Settings) -> Path:
    return settings.processed_dir / "shortlist_current.csv"


def current_parquet_path(settings: Settings) -> Path:
    return settings.processed_dir / "shortlist_current.parquet"


def history_csv_path(settings: Settings) -> Path:
    return settings.root / "data" / "history" / "shortlist_history.csv"


def history_parquet_path(settings: Settings) -> Path:
    return settings.root / "data" / "history" / "shortlist_history.parquet"


def alerts_path(settings: Settings) -> Path:
    return settings.processed_dir / "shortlist_alerts.csv"


def validation_path(settings: Settings) -> Path:
    return settings.processed_dir / "shortlist_validation_sample.csv"


def project_scale(gdv: Any, confidence: str | None) -> tuple[str, str, str]:
    if gdv is None or confidence in {None, "low", "unavailable"}:
        return (
            "Review required",
            "Review",
            "Reliable project GDV is unavailable, so the project is not automatically excluded",
        )
    value = Decimal(str(gdv))
    if value < Decimal("50000000"):
        return (
            "Below RM50m",
            "Below floor",
            "Reliable potential listed GDV is below the RM50m screening floor",
        )
    if value < Decimal("100000000"):
        return "RM50m–<RM100m", "Include", "Meets the RM50m project-GDV screening floor"
    if value < Decimal("500000000"):
        return "RM100m–<RM500m", "Include", "Core commercial-scale project GDV"
    if value < Decimal("1000000000"):
        return "RM500m–<RM1bn", "Include", "Large-scale project GDV"
    return "RM1bn+", "Include", "Major project GDV"


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _atomic_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})
    os.replace(temporary, path)


def _typed_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    connection = duckdb.connect(":memory:")
    try:
        columns_sql = ", ".join(f'"{name}" {sql_type}' for name, sql_type in SHORTLIST_FIELD_SPECS)
        connection.execute(f"CREATE TABLE metrics ({columns_sql})")
        placeholders = ",".join("?" for _ in SHORTLIST_FIELDS)
        connection.executemany(
            f"INSERT INTO metrics VALUES ({placeholders})",
            [
                [
                    None if row.get(field) in (None, "") else row.get(field)
                    for field in SHORTLIST_FIELDS
                ]
                for row in rows
            ],
        )
        escaped = str(temporary.resolve()).replace("'", "''")
        connection.execute(f"COPY metrics TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        connection.close()
    os.replace(temporary, path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _merge_history(settings: Settings, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history = _read_csv(history_csv_path(settings))
    current_keys = {(str(row["snapshot_date"]), str(row["source_project_id"])) for row in current}
    retained = [
        row
        for row in history
        if (str(row.get("snapshot_date")), str(row.get("source_project_id"))) not in current_keys
    ]
    merged: list[dict[str, Any]] = retained + current
    merged.sort(key=lambda row: (str(row.get("snapshot_date")), str(row.get("source_project_id"))))
    _atomic_csv(history_csv_path(settings), merged, SHORTLIST_FIELDS)
    _typed_parquet(history_parquet_path(settings), merged)
    return merged


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_alerts(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history:
        grouped[str(row.get("source_project_id") or "")].append(row)
    alerts: list[dict[str, str]] = []

    def add(row: dict[str, Any], severity: str, code: str, message: str) -> None:
        alerts.append(
            {
                "snapshot_date": str(row.get("snapshot_date") or ""),
                "region": str(row.get("region") or ""),
                "severity": severity,
                "alert_code": code,
                "source_project_id": str(row.get("source_project_id") or ""),
                "display_name": str(row.get("display_name") or row.get("project_name") or ""),
                "message": message,
            }
        )

    for project_rows in grouped.values():
        project_rows.sort(key=lambda row: str(row.get("snapshot_date") or ""))
        current = project_rows[-1]
        previous = project_rows[-2] if len(project_rows) > 1 else None
        status = str(current.get("project_status") or "")
        status_folded = status.casefold()
        if "sakit" in status_folded:
            add(current, "critical", "status_sakit", f"Current TEDUH status is {status}")
        if "lewat" in status_folded:
            add(current, "high", "status_lewat", f"Current TEDUH status is {status}")
        if "batal" in status_folded:
            add(current, "critical", "permit_cancelled", f"Current TEDUH status is {status}")
        if current.get("construction_confidence") == "unavailable":
            add(current, "info", "construction_unavailable", str(current.get("construction_note") or "Construction percentage is unavailable"))
        if previous is None:
            continue
        previous_status = str(previous.get("project_status") or "")
        if previous_status and status and previous_status != status:
            add(current, "high", "status_changed", f"Status changed from {previous_status} to {status}")
        current_sold = _number(current.get("sold_units"))
        previous_sold = _number(previous.get("sold_units"))
        if current_sold is not None and previous_sold is not None and current_sold < previous_sold:
            add(current, "high", "sold_units_decreased", f"Reported sold units decreased from {int(previous_sold)} to {int(current_sold)}")
        current_construction = _number(current.get("construction_percentage"))
        previous_construction = _number(previous.get("construction_percentage"))
        if (
            current_construction is not None
            and previous_construction is not None
            and current_construction < previous_construction
        ):
            add(current, "high", "construction_decreased", f"Construction percentage decreased from {previous_construction:g}% to {current_construction:g}%")
        if previous.get("ccc_obtained") == "No" and current.get("ccc_obtained") == "Yes":
            add(current, "info", "completion_certificate_obtained", "TEDUH now reports CCC/CFO completion evidence")
    severity_rank = {"critical": 0, "high": 1, "info": 2}
    alerts.sort(key=lambda row: (severity_rank.get(row["severity"], 9), row["display_name"].casefold()))
    return alerts


def _validation_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {str(row.get("source_project_id")): row for row in records}
    selected: list[dict[str, Any]] = []
    for role, code in VALIDATION_CODES:
        if code not in by_code:
            raise ValueError(f"Phase 3 validation project {code} is missing from the active shortlist snapshot")
        selected.append(dict(by_code[code], selection_role=role))
    if len(selected) != 5 or len({row["source_project_id"] for row in selected}) != 5:
        raise ValueError("Phase 3 validation sample must contain exactly five distinct projects")
    return selected


def snapshot_shortlist(
    settings: Settings,
    *,
    progress: Progress = print,
    project_progress: ProjectProgress | None = None,
) -> dict[str, Any]:
    today = date.today().isoformat()
    source_dataset_as_of = (date.today() - timedelta(days=1)).isoformat()
    shortlist = load_shortlist(settings, active_only=True)
    if not shortlist:
        raise ValueError("The active shortlist is empty")
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    progress(f"Refreshing {len(shortlist)} active TEDUH shortlist projects.")
    with TeduhClient(settings, snapshot_date=today, force=False) as client:
        for index, tracked in enumerate(shortlist, start=1):
            code = tracked["source_project_id"]
            try:
                detail_result = client.project_detail(code)
                detail = detail_result.payload
                project = detail.get("projek") or {}
                pjb = detail.get("pjb") or {}
                expected_state = str(REGION_CONFIGS[tracked["region"]]["state_label"])
                observed_state = normalize_state(project.get("negeri"))
                if observed_state != expected_state:
                    raise SourceAnomaly(
                        f"{code} is registered in {observed_state or 'an unknown state'}, "
                        f"not the selected {tracked['region']} region"
                    )
                if not is_hims_eligible(pjb.get("tarikhPjbPertama"), project.get("permitMula")):
                    raise SourceAnomaly(f"{code} predates comparable HIMS coverage")
                unit_result = client.project_units(code)
                developer = detail.get("pemaju") or {}
                status = detail.get("status") or {}
                search_project = {
                    "id": code,
                    "nama": detail.get("nama") or project.get("nama"),
                    "kod_pemaju": developer.get("kod_pemaju"),
                    "latest_lesen": developer.get("latest_lesen") or {},
                    "status_project": {"keterangan": status.get("keseluruhan")},
                }
                record = calculate_project_metrics(
                    search_project=search_project,
                    detail=detail,
                    units_payload=unit_result.payload,
                    city_lookup={},
                    snapshot_date=today,
                    source_dataset_as_of=source_dataset_as_of,
                    retrieved_at=max(detail_result.retrieved_at, unit_result.retrieved_at),
                )
                scale_band, commercial_scope, scope_reason = project_scale(
                    record.get("potential_listed_gdv"), str(record.get("gdv_confidence") or "")
                )
                record.update(
                    {
                        "region": tracked["region"],
                        "display_name": tracked["display_name"] or record.get("project_name") or code,
                        "parent_group": tracked["parent_group"],
                        "project_set": tracked["project_set"],
                        "manual_launch_date": tracked["manual_launch_date"],
                        "manual_built_up_min_sqft": tracked["manual_built_up_min_sqft"],
                        "manual_built_up_max_sqft": tracked["manual_built_up_max_sqft"],
                        "manual_psf_min": tracked["manual_psf_min"],
                        "manual_psf_max": tracked["manual_psf_max"],
                        "priority": tracked["priority"],
                        "tracking_notes": tracked["tracking_notes"],
                        "shortlist_active": tracked["active"],
                        "shortlist_origin": tracked["origin"],
                        "project_scale_band": scale_band,
                        "commercial_scope": commercial_scope,
                        "commercial_scope_reason": scope_reason,
                    }
                )
                records.append(record)
            except (SourceAnomaly, ValueError) as exc:
                failures.append(f"{code}: {exc}")
            if project_progress is not None:
                project_progress(index, len(shortlist))
            if index == 1 or index % 5 == 0 or index == len(shortlist):
                progress(f"Reviewed {index}/{len(shortlist)} shortlist projects.")
    if failures:
        preview = "; ".join(failures[:5])
        raise SourceAnomaly(f"Shortlist refresh failed for {len(failures)} project(s); valid outputs were preserved. {preview}")
    issues = validate_records(records)
    require_no_errors(issues)
    records.sort(
        key=lambda row: (
            str(row.get("region") or "").casefold(),
            str(row.get("display_name") or "").casefold(),
            str(row.get("source_project_id")),
        )
    )
    _atomic_csv(current_metrics_path(settings), records, SHORTLIST_FIELDS)
    _typed_parquet(current_parquet_path(settings), records)
    history = _merge_history(settings, records)
    alerts = build_alerts(history)
    _atomic_csv(alerts_path(settings), alerts, ALERT_FIELDS)
    validation = _validation_rows(records)
    _atomic_csv(validation_path(settings), validation, ["selection_role"] + SHORTLIST_FIELDS)
    progress("Shortlist snapshot, history, alerts, and exactly five validation rows were verified.")
    return {
        "snapshot_date": today,
        "project_count": len(records),
        "alert_count": len(alerts),
        "validation": validation,
        "paths": {
            "current_csv": current_metrics_path(settings),
            "current_parquet": current_parquet_path(settings),
            "history_csv": history_csv_path(settings),
            "history_parquet": history_parquet_path(settings),
            "alerts_csv": alerts_path(settings),
            "validation_csv": validation_path(settings),
        },
    }
