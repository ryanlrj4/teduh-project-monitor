from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Iterable

from .config import HIMS_UNIT_DATA_START_ISO


MONEY_FIELDS = (
    "potential_listed_gdv",
    "recorded_spa_sales_value",
    "estimated_sold_value",
    "remaining_listed_value",
    "minimum_indicative_gdv",
    "maximum_indicative_gdv",
)


def validate_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    seen_projects: set[tuple[str, str]] = set()
    for record in records:
        project_id = str(record.get("source_project_id") or "")
        snapshot_date = str(record.get("snapshot_date") or "")
        key = (project_id, snapshot_date)
        if not project_id:
            issues.append(_issue("error", project_id, "missing_project_id", "source_project_id is missing"))
        if not snapshot_date:
            issues.append(_issue("error", project_id, "missing_snapshot_date", "snapshot_date is missing"))
        if key in seen_projects:
            issues.append(_issue("error", project_id, "duplicate_project", "duplicate project within snapshot"))
        seen_projects.add(key)

        reference_date = str(record.get("hims_project_reference_date") or "")
        if not reference_date:
            issues.append(
                _issue(
                    "error",
                    project_id,
                    "missing_hims_reference_date",
                    "HIMS project reference date is missing",
                )
            )
        elif reference_date < HIMS_UNIT_DATA_START_ISO:
            issues.append(
                _issue(
                    "error",
                    project_id,
                    "legacy_project_in_output",
                    f"HIMS project reference date {reference_date} predates {HIMS_UNIT_DATA_START_ISO}",
                )
            )
        if record.get("ccc_obtained") not in {"Yes", "No"}:
            issues.append(
                _issue(
                    "error",
                    project_id,
                    "invalid_ccc_flag",
                    "ccc_obtained must be Yes or No",
                )
            )

        for field in ("reported_total_units", "unit_records_count", "sold_units", "unsold_units"):
            value = record.get(field)
            if value is not None and int(value) < 0:
                issues.append(_issue("error", project_id, "negative_count", f"{field} is negative"))

        for field in ("sales_percentage", "construction_percentage"):
            value = record.get(field)
            if value is not None and not (0 <= float(value) <= 100):
                issues.append(_issue("error", project_id, "percentage_out_of_range", f"{field} is outside 0-100"))

        if int(record.get("sold_units") or 0) > int(record.get("comparable_total_units") or 0):
            issues.append(_issue("error", project_id, "sold_exceeds_total", "sold units exceed comparable units"))

        for field in MONEY_FIELDS:
            value = record.get(field)
            if value is not None and Decimal(str(value)) < 0:
                issues.append(_issue("error", project_id, "negative_value", f"{field} is negative"))

        if int(record.get("duplicate_unit_identifiers") or 0) > 0:
            issues.append(_issue("warning", project_id, "duplicate_units", "duplicate unit identifiers detected"))
        if int(record.get("unknown_sales_status_units") or 0) > 0:
            issues.append(_issue("warning", project_id, "unknown_sales_status", "unknown sales statuses retained"))
        reported = record.get("reported_total_units")
        observed = record.get("unit_records_count")
        if reported is not None and int(reported) != int(observed or 0):
            issues.append(
                _issue(
                    "warning",
                    project_id,
                    "unit_reconciliation",
                    f"reported units {reported} differ from unit records {observed}",
                )
            )
        if record.get("construction_note"):
            issues.append(
                _issue(
                    "warning",
                    project_id,
                    "construction_unavailable",
                    str(record["construction_note"]),
                )
            )
    return issues


def _issue(severity: str, project_id: str, code: str, message: str) -> dict[str, str]:
    return {
        "severity": severity,
        "source_project_id": project_id,
        "code": code,
        "message": message,
    }


def require_no_errors(issues: Iterable[dict[str, str]]) -> None:
    errors = [issue for issue in issues if issue["severity"] == "error"]
    if errors:
        preview = "; ".join(f"{item['source_project_id']}: {item['message']}" for item in errors[:5])
        raise ValueError(f"Validation found {len(errors)} error(s): {preview}")


def select_exactly_five(records: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    by_status: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_status.setdefault(str(record.get("project_status") or ""), []).append(record)

    def highest_units(status: str) -> dict[str, Any]:
        candidates = by_status.get(status, [])
        if not candidates:
            raise ValueError(f"Cannot select validation project: no {status} project was retrieved")
        return max(
            candidates,
            key=lambda row: (
                int(row.get("reported_total_units") or -1),
                int(row.get("unit_records_count") or -1),
                str(row.get("source_project_id")),
            ),
        )

    running = by_status.get("Lancar", [])
    if len(running) < 2:
        raise ValueError("Cannot select exactly two distinct Lancar validation projects")
    complete = sorted(
        running,
        key=lambda row: (
            row.get("unit_coverage_percentage") == 100.0,
            row.get("listed_price_coverage_percentage") == 100.0,
            int(row.get("sold_units") or 0),
            int(row.get("reported_total_units") or 0),
            str(row.get("source_project_id")),
        ),
        reverse=True,
    )[0]
    mid_sales_candidates = [row for row in running if row is not complete]
    mid_sales = min(
        mid_sales_candidates,
        key=lambda row: (
            abs(float(row.get("sales_percentage") or 0) - 50.0),
            -int(row.get("reported_total_units") or 0),
            str(row.get("source_project_id")),
        ),
    )

    selected = [
        ("not_started", highest_units("Belum Mula")),
        ("active_data_rich", complete),
        ("active_mid_sales", mid_sales),
        ("delayed", highest_units("Lewat")),
        ("sick", highest_units("Sakit")),
    ]
    ids = [row["source_project_id"] for _, row in selected]
    if len(selected) != 5 or len(set(ids)) != 5:
        raise ValueError(f"Validation selection must contain exactly five distinct projects; got {ids}")
    return selected


def issue_counts(issues: list[dict[str, str]]) -> Counter[str]:
    return Counter(issue["code"] for issue in issues)
