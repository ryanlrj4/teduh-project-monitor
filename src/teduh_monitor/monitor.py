from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .collection import collect_project
from .config import REGION_CONFIGS, Settings
from .refresh_status import (
    complete_refresh_failure,
    complete_refresh_success,
    start_refresh,
    update_refresh,
)
from .sources import SourceAnomaly, TeduhClient
from .validate import require_no_errors, validate_records
from .shortlist import load_shortlist
from .schema import ALERT_FIELDS, SHORTLIST_FIELD_SPECS, SHORTLIST_FIELDS
from .storage import atomic_write_csv, atomic_write_parquet, read_csv


Progress = Callable[[str], None]
ProjectProgress = Callable[[int, int, str, bool], None]


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


def _merge_history(settings: Settings, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history = read_csv(history_csv_path(settings))
    current_keys = {(str(row["snapshot_date"]), str(row["source_project_id"])) for row in current}
    retained = [
        row
        for row in history
        if (str(row.get("snapshot_date")), str(row.get("source_project_id"))) not in current_keys
    ]
    merged: list[dict[str, Any]] = retained + current
    merged.sort(key=lambda row: (str(row.get("snapshot_date")), str(row.get("source_project_id"))))
    atomic_write_csv(history_csv_path(settings), merged, SHORTLIST_FIELDS)
    atomic_write_parquet(
        history_parquet_path(settings),
        merged,
        SHORTLIST_FIELD_SPECS,
        blank_as_none=True,
    )
    return merged


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _days_until(snapshot_date: Any, future_date: Any) -> int | None:
    try:
        return (date.fromisoformat(str(future_date)) - date.fromisoformat(str(snapshot_date))).days
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
            add(current, "critical", "status_sakit", f"TEDUH status: {status}")
        if "lewat" in status_folded:
            add(current, "high", "status_lewat", f"TEDUH status: {status}")
        if "batal" in status_folded:
            add(current, "critical", "permit_cancelled", f"TEDUH status: {status}")
        if current.get("construction_confidence") == "unavailable":
            add(current, "info", "construction_unavailable", str(current.get("construction_note") or "Construction percentage is unavailable"))
        completed = "siap dengan" in status_folded
        permit_days = _days_until(current.get("snapshot_date"), current.get("permit_end_date"))
        if not completed and permit_days is not None:
            if permit_days < 0:
                add(current, "high", "permit_expired", "Advertising and sales permit expired")
            elif permit_days <= 90:
                add(current, "info", "permit_expiring", f"Current advertising and sales permit expires in {permit_days} day(s)")
        licence_days = _days_until(
            current.get("snapshot_date"), current.get("developer_license_end_date")
        )
        if licence_days is not None:
            if licence_days < 0:
                add(current, "high", "developer_licence_expired", "Developer licence expired")
            elif licence_days <= 90:
                add(current, "info", "developer_licence_expiring", f"Developer licence expires in {licence_days} day(s)")
        developer_status = str(current.get("developer_status") or "").strip()
        if developer_status and developer_status.casefold() not in {"aktif", "active"}:
            add(current, "high", "developer_inactive", f"Developer status: {developer_status}")
        sales_gap = _number(current.get("sales_construction_gap"))
        if sales_gap is not None and sales_gap <= -25:
            add(
                current,
                "info",
                "sales_lags_construction",
                f"Unit sales trail construction progress by {abs(sales_gap):g} percentage points",
            )
        if previous is None:
            continue
        previous_status = str(previous.get("project_status") or "")
        if previous_status and status and previous_status != status:
            add(current, "high", "status_changed", f"Status: {previous_status} → {status}")
        current_sold = _number(current.get("sold_units"))
        previous_sold = _number(previous.get("sold_units"))
        if current_sold is not None and previous_sold is not None and current_sold < previous_sold:
            add(current, "high", "sold_units_decreased", f"Units sold: {int(previous_sold)} → {int(current_sold)}")
        current_construction = _number(current.get("construction_percentage"))
        previous_construction = _number(previous.get("construction_percentage"))
        if (
            current_construction is not None
            and previous_construction is not None
            and current_construction < previous_construction
        ):
            add(current, "high", "construction_decreased", f"Construction: {previous_construction:g}% → {current_construction:g}%")
        if previous.get("ccc_obtained") == "No" and current.get("ccc_obtained") == "Yes":
            add(current, "info", "completion_certificate_obtained", "TEDUH now reports CCC/CFO completion evidence")
    severity_rank = {"critical": 0, "high": 1, "info": 2}
    alerts.sort(key=lambda row: (severity_rank.get(row["severity"], 9), row["display_name"].casefold()))
    return alerts


def _snapshot_shortlist(
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
    cached_project_count = 0
    live_project_count = 0
    progress(f"Refreshing {len(shortlist)} active TEDUH shortlist projects.")
    with TeduhClient(settings, snapshot_date=today, force=False) as client:
        for index, tracked in enumerate(shortlist, start=1):
            code = tracked["source_project_id"]
            project_succeeded = False
            try:
                expected_state = str(REGION_CONFIGS[tracked["region"]]["state_label"])
                collected = collect_project(
                    client,
                    project_code=code,
                    snapshot_date=today,
                    source_dataset_as_of=source_dataset_as_of,
                    expected_state=expected_state,
                    expected_region=tracked["region"],
                )
                record = collected.record
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
                        "tracking_notes": tracked["tracking_notes"],
                        "shortlist_active": tracked["active"],
                        "shortlist_origin": tracked["origin"],
                        "project_scale_band": scale_band,
                        "commercial_scope": commercial_scope,
                        "commercial_scope_reason": scope_reason,
                    }
                )
                records.append(record)
                project_succeeded = True
                if collected.detail_from_cache and collected.units_from_cache:
                    cached_project_count += 1
                else:
                    live_project_count += 1
            except (SourceAnomaly, ValueError) as exc:
                failures.append(f"{code}: {exc}")
            if project_progress is not None:
                project_progress(index, len(shortlist), code, project_succeeded)
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
    atomic_write_csv(current_metrics_path(settings), records, SHORTLIST_FIELDS)
    atomic_write_parquet(
        current_parquet_path(settings),
        records,
        SHORTLIST_FIELD_SPECS,
        blank_as_none=True,
    )
    history = _merge_history(settings, records)
    alerts = build_alerts(history)
    atomic_write_csv(alerts_path(settings), alerts, ALERT_FIELDS)
    progress("Shortlist snapshot, history, and alerts were validated and published.")
    return {
        "snapshot_date": today,
        "source_dataset_as_of": source_dataset_as_of,
        "project_count": len(records),
        "cached_project_count": cached_project_count,
        "live_project_count": live_project_count,
        "alert_count": len(alerts),
        "paths": {
            "current_csv": current_metrics_path(settings),
            "current_parquet": current_parquet_path(settings),
            "history_csv": history_csv_path(settings),
            "history_parquet": history_parquet_path(settings),
            "alerts_csv": alerts_path(settings),
        },
    }


def snapshot_shortlist(
    settings: Settings,
    *,
    progress: Progress = print,
    project_progress: ProjectProgress | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    total_projects = len(load_shortlist(settings, active_only=True))
    start_refresh(settings, trigger=trigger, total_projects=total_projects)
    successful_projects = 0
    failed_projects = 0

    def tracked_progress(completed: int, total: int, code: str, succeeded: bool) -> None:
        nonlocal successful_projects, failed_projects
        if succeeded:
            successful_projects += 1
        else:
            failed_projects += 1
        update_refresh(
            settings,
            completed_projects=completed,
            successful_projects=successful_projects,
            failed_projects=failed_projects,
            current_project_code=code,
        )
        if project_progress is not None:
            project_progress(completed, total, code, succeeded)

    try:
        result = _snapshot_shortlist(
            settings,
            progress=progress,
            project_progress=tracked_progress,
        )
    except Exception as exc:
        complete_refresh_failure(settings, error=exc)
        raise
    complete_refresh_success(settings, result=result)
    return result
