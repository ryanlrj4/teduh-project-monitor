from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .collection import IneligibleProject, collect_project
from .config import HIMS_UNIT_DATA_START_ISO, Settings, TARGET_STATUSES
from .full_catalog_export import export_full_catalog_outputs
from .sources import SourceAnomaly, TeduhClient, fetch_project_catalog
from .storage import atomic_write_json, read_json
from .validate import require_no_errors, validate_records


Progress = Callable[[str], None]


def select_validation_sample(
    records: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    by_status: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_status.setdefault(str(record.get("project_status") or ""), []).append(record)

    def highest_units(status: str) -> dict[str, Any]:
        candidates = by_status.get(status, [])
        if not candidates:
            raise ValueError(
                f"Cannot select validation project: no {status} project was retrieved"
            )
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
    mid_sales = min(
        (row for row in running if row is not complete),
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
    if len(set(ids)) != 5:
        raise ValueError(
            f"Validation selection must contain exactly five distinct projects; got {ids}"
        )
    return selected


def _read_previous_manifest(path: Path) -> dict[str, Any] | None:
    payload = read_json(path, None, tolerate_invalid=False)
    return payload if isinstance(payload, dict) else None


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload, ensure_ascii=True)


def run_full_catalog_proof(
    settings: Settings,
    *,
    force: bool = False,
    progress: Progress = print,
) -> dict[str, Any]:
    snapshot_date = date.today().isoformat()
    source_dataset_as_of = (date.today() - timedelta(days=1)).isoformat()
    anomalies: list[str] = []
    progress(f"Starting TEDUH snapshot {snapshot_date}; requests are sequential and cached.")

    with TeduhClient(settings, snapshot_date=snapshot_date, force=force) as client:
        states = client.states().payload
        if not any(str(row.get("id")) == "14" and str(row.get("keterangan")).casefold() == "wp kuala lumpur" for row in states):
            raise SourceAnomaly("TEDUH state lookup no longer contains id 14 = WP Kuala Lumpur")
        districts = client.districts().payload
        city_lookup: dict[str, str] = {}
        for district in districts:
            district_id = str(district.get("id") or "")
            if not district_id:
                continue
            for city in client.cities(district_id).payload:
                city_lookup[str(city.get("id"))] = str(city.get("keterangan"))

        catalog, counts = fetch_project_catalog(client)
        total = len(catalog)
        expected_count = sum(counts.values())
        if total != expected_count:
            raise SourceAnomaly(f"Unique project count {total} differs from status total {expected_count}")
        previous_manifest = _read_previous_manifest(settings.interim_dir / "last_success.json")
        if previous_manifest:
            previous_total = int(
                previous_manifest.get("catalog_project_count")
                or previous_manifest.get("project_count")
                or 0
            )
            if previous_total and total < previous_total * settings.major_count_decrease_ratio:
                raise SourceAnomaly(
                    f"Project count fell from {previous_total} to {total}, below the "
                    f"{settings.major_count_decrease_ratio:.0%} safety threshold"
                )
        progress(
            "Catalog confirmed: "
            + ", ".join(f"{status}={counts[status]}" for status in TARGET_STATUSES.values())
            + f"; total={total}."
        )

        records: list[dict[str, Any]] = []
        excluded_legacy_projects = 0
        failed_details = 0
        failed_units = 0
        for index, search_project in enumerate(catalog, start=1):
            project_code = str(search_project["id"])
            try:
                collected = collect_project(
                    client,
                    project_code=project_code,
                    search_project=search_project,
                    city_lookup=city_lookup,
                    snapshot_date=snapshot_date,
                    source_dataset_as_of=source_dataset_as_of,
                    allow_missing_units=True,
                )
            except IneligibleProject:
                excluded_legacy_projects += 1
            except SourceAnomaly as exc:
                failed_details += 1
                anomalies.append(f"{project_code} detail: {exc}")
            else:
                if collected.unit_error is not None:
                    failed_units += 1
                    anomalies.append(f"{project_code} units: {collected.unit_error}")
                records.append(collected.record)
            if index == 1 or index % 10 == 0 or index == total:
                progress(f"Reviewed {index}/{total} catalog projects (latest: {project_code}).")

    if failed_details:
        raise SourceAnomaly(
            f"{failed_details} project detail requests failed, so HIMS eligibility could not be determined; "
            "refusing to publish outputs"
        )
    eligible_total = len(records)
    if failed_units > max(5, int(eligible_total * 0.10)):
        raise SourceAnomaly(f"{failed_units} unit requests failed; refusing to publish outputs")
    if not records:
        raise SourceAnomaly(
            f"No projects met the HIMS eligibility cutoff of {HIMS_UNIT_DATA_START_ISO}; "
            "refusing to publish outputs"
        )
    if sum(int(row.get("unit_records_count") or 0) for row in records) == 0:
        raise SourceAnomaly("All unit endpoints returned zero units; refusing to publish outputs")

    eligible_counts = {
        status: sum(row.get("project_status") == status for row in records)
        for status in TARGET_STATUSES.values()
    }
    progress(
        f"HIMS eligibility filter retained {eligible_total} projects and excluded "
        f"{excluded_legacy_projects} legacy projects before {HIMS_UNIT_DATA_START_ISO}."
    )

    issues = validate_records(records)
    require_no_errors(issues)
    selected = select_validation_sample(records)
    paths = export_full_catalog_outputs(
        settings,
        records,
        selected,
        eligible_counts,
        issues,
        anomalies,
        catalog_project_count=total,
        excluded_legacy_projects=excluded_legacy_projects,
    )
    _write_manifest(
        settings.interim_dir / "last_success.json",
        {
            "snapshot_date": snapshot_date,
            "catalog_project_count": total,
            "project_count": eligible_total,
            "excluded_legacy_projects": excluded_legacy_projects,
            "status_counts": eligible_counts,
            "validation_project_ids": [row["source_project_id"] for _, row in selected],
            "outputs": {name: str(path) for name, path in paths.items()},
        },
    )
    progress("Outputs verified. Exactly five validation projects were selected.")
    return {
        "snapshot_date": snapshot_date,
        "catalog_project_count": total,
        "project_count": eligible_total,
        "excluded_legacy_projects": excluded_legacy_projects,
        "status_counts": eligible_counts,
        "issues": issues,
        "anomalies": anomalies,
        "validation": [dict(record, selection_role=role) for role, record in selected],
        "paths": paths,
    }
