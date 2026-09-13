from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Iterable

from .config import HIMS_UNIT_DATA_START_ISO


MONEY_FIELDS = (
    "potential_listed_gdv",
    "average_listed_price_per_unit",
    "median_listed_price_per_unit",
    "listed_price_p25",
    "listed_price_p75",
    "sold_listed_value",
    "recorded_spa_sales_value",
    "average_recorded_spa_price_per_unit",
    "median_recorded_spa_price_per_unit",
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

        for field in (
            "reported_total_units",
            "unit_records_count",
            "sold_units",
            "unsold_units",
            "booked_or_reserved_units",
            "unknown_sales_status_units",
            "bumi_total_units",
            "bumi_sold_units",
            "bumi_unsold_units",
        ):
            value = record.get(field)
            if value is not None and int(value) < 0:
                issues.append(_issue("error", project_id, "negative_count", f"{field} is negative"))

        for field in ("sales_percentage", "construction_percentage", "bumi_sales_percentage"):
            value = record.get(field)
            if value is not None and not (0 <= float(value) <= 100):
                issues.append(_issue("error", project_id, "percentage_out_of_range", f"{field} is outside 0-100"))

        if int(record.get("sold_units") or 0) > int(record.get("comparable_total_units") or 0):
            issues.append(_issue("error", project_id, "sold_exceeds_total", "sold units exceed comparable units"))
        if int(record.get("bumi_sold_units") or 0) + int(
            record.get("bumi_unsold_units") or 0
        ) > int(record.get("bumi_total_units") or 0):
            issues.append(
                _issue(
                    "error",
                    project_id,
                    "bumi_sales_exceed_total",
                    "Bumiputera sold and available units exceed the Bumiputera total",
                )
            )

        for field in ("value_sold_percentage", "recorded_price_realisation_percentage"):
            value = record.get(field)
            if value is not None and float(value) < 0:
                issues.append(
                    _issue("error", project_id, "negative_percentage", f"{field} is negative")
                )
        gap = record.get("sales_construction_gap")
        if gap is not None and not (-100 <= float(gap) <= 100):
            issues.append(
                _issue(
                    "error",
                    project_id,
                    "gap_out_of_range",
                    "sales_construction_gap is outside -100 to 100",
                )
            )

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


def issue_counts(issues: list[dict[str, str]]) -> Counter[str]:
    return Counter(issue["code"] for issue in issues)
