from __future__ import annotations

import csv
import os
import shutil
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .config import HIMS_UNIT_DATA_START_ISO, SEARCH_PAGE_URL, Settings
from .validate import issue_counts


FIELD_SPECS: list[tuple[str, str]] = [
    ("snapshot_date", "DATE"),
    ("source", "VARCHAR"),
    ("source_project_id", "VARCHAR"),
    ("project_name", "VARCHAR"),
    ("developer_id", "VARCHAR"),
    ("developer_name", "VARCHAR"),
    ("state", "VARCHAR"),
    ("district", "VARCHAR"),
    ("city", "VARCHAR"),
    ("source_state_value", "VARCHAR"),
    ("source_district_value", "VARCHAR"),
    ("source_city_value", "VARCHAR"),
    ("permit_number", "VARCHAR"),
    ("permit_start_date", "DATE"),
    ("permit_end_date", "DATE"),
    ("first_spa_date", "DATE"),
    ("teduh_spa_price_min", "DECIMAL(24,2)"),
    ("teduh_spa_price_max", "DECIMAL(24,2)"),
    ("hims_project_reference_date", "DATE"),
    ("hims_project_reference_date_basis", "VARCHAR"),
    ("hims_eligibility_cutoff_date", "DATE"),
    ("project_status", "VARCHAR"),
    ("expected_vp_date", "DATE"),
    ("revised_vp_date", "DATE"),
    ("ccc_obtained", "VARCHAR"),
    ("ccc_date", "DATE"),
    ("vp_date", "DATE"),
    ("reported_total_units", "BIGINT"),
    ("unit_records_count", "BIGINT"),
    ("priced_unit_records_count", "BIGINT"),
    ("sold_units", "BIGINT"),
    ("unsold_units", "BIGINT"),
    ("comparable_total_units", "BIGINT"),
    ("sales_percentage", "DOUBLE"),
    ("construction_percentage", "DOUBLE"),
    ("potential_listed_gdv", "DECIMAL(24,2)"),
    ("recorded_spa_sales_value", "DECIMAL(24,2)"),
    ("estimated_sold_value", "DECIMAL(24,2)"),
    ("remaining_listed_value", "DECIMAL(24,2)"),
    ("minimum_indicative_gdv", "DECIMAL(24,2)"),
    ("maximum_indicative_gdv", "DECIMAL(24,2)"),
    ("unit_coverage_percentage", "DOUBLE"),
    ("listed_price_coverage_percentage", "DOUBLE"),
    ("spa_price_coverage_percentage", "DOUBLE"),
    ("duplicate_unit_identifiers", "BIGINT"),
    ("construction_row_units", "BIGINT"),
    ("construction_row_count", "BIGINT"),
    ("gdv_confidence", "VARCHAR"),
    ("sales_percentage_confidence", "VARCHAR"),
    ("sales_value_confidence", "VARCHAR"),
    ("construction_confidence", "VARCHAR"),
    ("construction_note", "VARCHAR"),
    ("source_url", "VARCHAR"),
    ("source_detail_api_url", "VARCHAR"),
    ("source_units_api_url", "VARCHAR"),
    ("source_dataset_as_of", "DATE"),
    ("source_dataset_as_of_method", "VARCHAR"),
    ("retrieved_at", "VARCHAR"),
    ("transformation_version", "VARCHAR"),
    ("construction_rows_json", "VARCHAR"),
]
FIELDS = [name for name, _ in FIELD_SPECS]

VALIDATION_FIELDS = [
    "selection_role",
    "source_project_id",
    "project_name",
    "developer_id",
    "developer_name",
    "snapshot_date",
    "source_dataset_as_of",
    "project_status",
    "first_spa_date",
    "teduh_spa_price_min",
    "teduh_spa_price_max",
    "hims_project_reference_date",
    "hims_project_reference_date_basis",
    "hims_eligibility_cutoff_date",
    "reported_total_units",
    "unit_records_count",
    "sold_units",
    "unsold_units",
    "sales_percentage",
    "construction_percentage",
    "potential_listed_gdv",
    "recorded_spa_sales_value",
    "estimated_sold_value",
    "remaining_listed_value",
    "unit_coverage_percentage",
    "listed_price_coverage_percentage",
    "spa_price_coverage_percentage",
    "gdv_confidence",
    "sales_percentage_confidence",
    "sales_value_confidence",
    "construction_confidence",
    "permit_number",
    "permit_start_date",
    "permit_end_date",
    "expected_vp_date",
    "revised_vp_date",
    "ccc_obtained",
    "ccc_date",
    "vp_date",
    "source_url",
    "source_detail_api_url",
    "source_units_api_url",
    "comparison_notes",
]


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    connection = duckdb.connect(":memory:")
    try:
        columns_sql = ", ".join(f'"{name}" {sql_type}' for name, sql_type in FIELD_SPECS)
        connection.execute(f"CREATE TABLE metrics ({columns_sql})")
        placeholders = ",".join("?" for _ in FIELDS)
        connection.executemany(
            f"INSERT INTO metrics VALUES ({placeholders})",
            [[row.get(field) for field in FIELDS] for row in rows],
        )
        escaped = str(path.resolve()).replace("'", "''")
        connection.execute(f"COPY metrics TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        count = connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        if count != len(rows):
            raise RuntimeError(f"Parquet staging row count {count} does not match {len(rows)}")
    finally:
        connection.close()


def _comparison_notes(record: dict[str, Any]) -> str:
    notes: list[str] = []
    if record.get("reported_total_units") != record.get("unit_records_count"):
        notes.append("Reported and observed unit counts do not reconcile")
    if record.get("unknown_sales_status_units"):
        notes.append("Unknown sales statuses retained")
    if record.get("construction_percentage") is None:
        notes.append(record.get("construction_note") or "Construction aggregation unavailable")
    if record.get("potential_listed_gdv") is None:
        notes.append("Potential listed GDV withheld because coverage rules did not pass")
    if not notes:
        notes.append("Automated counts and coverage checks reconcile; manual TEDUH comparison required")
    return "; ".join(notes)


def build_validation_rows(
    selected: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    rows = []
    for role, record in selected:
        row = dict(record)
        row["selection_role"] = role
        row["comparison_notes"] = _comparison_notes(record)
        rows.append(row)
    if len(rows) != 5:
        raise ValueError(f"Validation output must have exactly five rows, got {len(rows)}")
    return rows


def _coverage_bucket(value: Any) -> str:
    if value is None:
        return "unavailable"
    number = float(value)
    if number == 0:
        return "0%"
    if number < 50:
        return ">0% to <50%"
    if number < 95:
        return "50% to <95%"
    if number < 100:
        return "95% to <100%"
    if number == 100:
        return "100%"
    return ">100%"


def data_quality_report(
    records: list[dict[str, Any]],
    counts: dict[str, int],
    issues: list[dict[str, str]],
    anomalies: list[str],
    *,
    catalog_project_count: int,
    excluded_legacy_projects: int,
) -> str:
    unit_distribution = Counter(_coverage_bucket(row.get("unit_coverage_percentage")) for row in records)
    price_distribution = Counter(
        _coverage_bucket(row.get("listed_price_coverage_percentage")) for row in records
    )
    issue_summary = issue_counts(issues)
    missing_fields = [
        "developer_id",
        "developer_name",
        "district",
        "city",
        "permit_number",
        "expected_vp_date",
        "revised_vp_date",
        "potential_listed_gdv",
        "recorded_spa_sales_value",
    ]
    missing_lines = []
    for field in missing_fields:
        missing = sum(row.get(field) in (None, "") for row in records)
        missing_lines.append(f"| `{field}` | {missing} | {missing / len(records) * 100:.2f}% |")
    status_lines = "\n".join(f"| {status} | {count} |" for status, count in counts.items())
    unit_lines = "\n".join(f"| {bucket} | {count} |" for bucket, count in sorted(unit_distribution.items()))
    price_lines = "\n".join(f"| {bucket} | {count} |" for bucket, count in sorted(price_distribution.items()))
    issue_lines = "\n".join(f"| `{code}` | {count} |" for code, count in sorted(issue_summary.items())) or "| None | 0 |"
    anomaly_lines = "\n".join(f"- {item}" for item in anomalies) or "- No retrieval anomalies were recorded."
    return f"""# Data Quality Report

Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}

## Scope

- Source: TEDUH only
- Location: WP Kuala Lumpur (`state=14`)
- Included statuses: Belum Mula, Lancar, Sakit, Lewat
- HIMS unit-data cutoff: **{HIMS_UNIT_DATA_START_ISO}**
- Eligibility date: first PJB/SPA date when present; permit start date otherwise
- TEDUH catalog projects reviewed: **{catalog_project_count}**
- Legacy projects excluded: **{excluded_legacy_projects}**
- Eligible project rows: **{len(records)}**

## Projects by status

| Status | Projects |
|---|---:|
{status_lines}

## Unit coverage distribution

| Coverage | Projects |
|---|---:|
{unit_lines}

## Listed-price coverage distribution

| Coverage | Projects |
|---|---:|
{price_lines}

## Validation findings

| Finding | Projects/occurrences |
|---|---:|
{issue_lines}

- Unknown-status unit count: **{sum(int(row.get('unknown_sales_status_units') or 0) for row in records)}**
- Duplicate unit identifier count: **{sum(int(row.get('duplicate_unit_identifiers') or 0) for row in records)}**
- Unit reconciliation failures: **{sum(row.get('reported_total_units') is not None and row.get('reported_total_units') != row.get('unit_records_count') for row in records)}**
- CCC obtained = Yes: **{sum(row.get('ccc_obtained') == 'Yes' for row in records)}**
- CCC obtained = No: **{sum(row.get('ccc_obtained') == 'No' for row in records)}**

## Missing-field rates

| Field | Missing | Rate |
|---|---:|---:|
{chr(10).join(missing_lines)}

## Retrieval anomalies

{anomaly_lines}

## Important limitations

- TEDUH unit statuses are developer-maintained HIMS data and require manual confirmation for purchasing decisions.
- Projects whose first PJB/SPA date predates {HIMS_UNIT_DATA_START_ISO} are excluded. When that date is unavailable, permit start is the fallback.
- The displayed HIMS date is generated by the frontend as the previous day; it is not returned as an authoritative API timestamp.
- A missing SPA price is retained as missing, never converted to zero.
- Potential listed GDV is a unit-price sum, not audited or official developer GDV.
- Construction is aggregated only when row groups are unique and their unit counts reconcile.
- District and city values are incomplete and administratively inconsistent, so the state code is the primary KL filter.
"""


def validation_report(validation_rows: list[dict[str, Any]]) -> str:
    if len(validation_rows) != 5:
        raise ValueError("Validation report requires exactly five projects")
    lines = []
    for row in validation_rows:
        lines.append(
            "| {role} | `{code}` | {name} | {status} | {reported} | {observed} | {sold} | {sales} | {construction} | {gdv} |".format(
                role=row["selection_role"],
                code=row["source_project_id"],
                name=str(row.get("project_name") or "-").replace("|", "\\|"),
                status=row.get("project_status") or "-",
                reported=row.get("reported_total_units") if row.get("reported_total_units") is not None else "-",
                observed=row.get("unit_records_count"),
                sold=row.get("sold_units"),
                sales=f"{row['sales_percentage']:.4f}%" if row.get("sales_percentage") is not None else "-",
                construction=f"{row['construction_percentage']:.2f}%" if row.get("construction_percentage") is not None else "-",
                gdv=_csv_value(row.get("potential_listed_gdv")) or "-",
            )
        )
    detail_sections = []
    for row in validation_rows:
        detail_sections.append(
            f"""### {row['source_project_id']} — {row.get('project_name') or '-'}

- Selection role: `{row['selection_role']}`
- Developer: `{row.get('developer_id') or '-'}` — {row.get('developer_name') or '-'}
- Source snapshot: {row.get('snapshot_date')}; displayed HIMS as-of: {row.get('source_dataset_as_of')}
- HIMS eligibility: {row.get('hims_project_reference_date')} via `{row.get('hims_project_reference_date_basis')}`; cutoff {row.get('hims_eligibility_cutoff_date')}
- CCC obtained (at least one component): {row.get('ccc_obtained')}
- Unit coverage: {row.get('unit_coverage_percentage') if row.get('unit_coverage_percentage') is not None else '-'}%
- Listed-price coverage: {row.get('listed_price_coverage_percentage') if row.get('listed_price_coverage_percentage') is not None else '-'}%
- SPA-price coverage among sold units: {row.get('spa_price_coverage_percentage') if row.get('spa_price_coverage_percentage') is not None else '-'}%
- Confidence: GDV `{row.get('gdv_confidence')}`, sales percentage `{row.get('sales_percentage_confidence')}`, sales value `{row.get('sales_value_confidence')}`, construction `{row.get('construction_confidence')}`
- Automated comparison note: {row.get('comparison_notes')}
- [TEDUH project detail API]({row.get('source_detail_api_url')})
- [TEDUH unit API]({row.get('source_units_api_url')})
"""
        )
    return f"""# Validation Report

Exactly five projects were selected by fixed roles. This is the complete validation sample; no additional projects are included.

| Role | Code | Project | Status | Reported units | Unit rows | Sold | Sales % | Construction % | Potential listed GDV (RM) |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(lines)}

## Manual comparison instructions

Open each linked TEDUH record and compare the project/developer identity, permit, reported units, unit statuses, prices, PJB dates, and construction rows. Do not approve this data proof solely from the calculated fields.

{chr(10).join(detail_sections)}
"""


def export_outputs(
    settings: Settings,
    records: list[dict[str, Any]],
    selected: list[tuple[str, dict[str, Any]]],
    counts: dict[str, int],
    issues: list[dict[str, str]],
    anomalies: list[str],
    *,
    catalog_project_count: int,
    excluded_legacy_projects: int,
) -> dict[str, Path]:
    staging = settings.processed_dir / f".staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    validation_rows = build_validation_rows(selected)
    staged_metrics_csv = staging / "kl_project_metrics_hims_eligible.csv"
    staged_metrics_parquet = staging / "kl_project_metrics_hims_eligible.parquet"
    staged_validation = staging / "kl_validation_sample_hims_eligible.csv"
    staged_quality = staging / "DATA_QUALITY_REPORT.md"
    staged_validation_report = staging / "VALIDATION_REPORT.md"
    try:
        _write_csv(staged_metrics_csv, records, FIELDS)
        _write_parquet(staged_metrics_parquet, records)
        _write_csv(staged_validation, validation_rows, VALIDATION_FIELDS)
        staged_quality.write_text(
            data_quality_report(
                records,
                counts,
                issues,
                anomalies,
                catalog_project_count=catalog_project_count,
                excluded_legacy_projects=excluded_legacy_projects,
            ),
            encoding="utf-8",
        )
        staged_validation_report.write_text(validation_report(validation_rows), encoding="utf-8")

        with staged_metrics_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            csv_count = sum(1 for _ in csv.DictReader(handle))
        with staged_validation.open("r", encoding="utf-8-sig", newline="") as handle:
            validation_count = sum(1 for _ in csv.DictReader(handle))
        parquet_count = duckdb.connect(":memory:").execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(staged_metrics_parquet)]
        ).fetchone()[0]
        if csv_count != len(records) or parquet_count != len(records):
            raise RuntimeError("CSV/Parquet verification count mismatch")
        if validation_count != 5:
            raise RuntimeError(f"Validation CSV contains {validation_count} rows instead of exactly five")

        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        settings.docs_dir.mkdir(parents=True, exist_ok=True)
        destinations = {
            "metrics_csv": settings.processed_dir / "kl_project_metrics_hims_eligible.csv",
            "metrics_parquet": settings.processed_dir / "kl_project_metrics_hims_eligible.parquet",
            "validation_csv": settings.processed_dir / "kl_validation_sample_hims_eligible.csv",
            "quality_report": settings.docs_dir / "DATA_QUALITY_REPORT.md",
            "validation_report": settings.docs_dir / "VALIDATION_REPORT.md",
        }
        os.replace(staged_metrics_csv, destinations["metrics_csv"])
        os.replace(staged_metrics_parquet, destinations["metrics_parquet"])
        os.replace(staged_validation, destinations["validation_csv"])
        os.replace(staged_quality, destinations["quality_report"])
        os.replace(staged_validation_report, destinations["validation_report"])
        return destinations
    finally:
        if staging.exists():
            shutil.rmtree(staging)
