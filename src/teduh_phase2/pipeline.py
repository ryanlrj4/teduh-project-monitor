from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .config import HIMS_UNIT_DATA_START_ISO, Settings, TARGET_STATUSES
from .export import export_outputs
from .metrics import calculate_project_metrics
from .normalize import is_hims_eligible
from .sources import SourceAnomaly, TeduhClient, fetch_project_catalog
from .storage import atomic_write_json, read_json
from .validate import require_no_errors, select_exactly_five, validate_records


Progress = Callable[[str], None]


def _read_previous_manifest(path: Path) -> dict[str, Any] | None:
    payload = read_json(path, None, tolerate_invalid=False)
    return payload if isinstance(payload, dict) else None


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload, ensure_ascii=True)


def run_pipeline(
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
            detail_payload: dict[str, Any] | None = None
            units_payload: dict[str, Any] | None = None
            retrieved_at = date.today().isoformat()
            try:
                detail_result = client.project_detail(project_code)
                detail_payload = detail_result.payload
                retrieved_at = detail_result.retrieved_at
            except SourceAnomaly as exc:
                failed_details += 1
                anomalies.append(f"{project_code} detail: {exc}")
            if detail_payload is None:
                if index == 1 or index % 10 == 0 or index == total:
                    progress(f"Reviewed {index}/{total} catalog projects (latest: {project_code}).")
                continue

            project = detail_payload.get("projek") or {}
            pjb = detail_payload.get("pjb") or {}
            if not is_hims_eligible(pjb.get("tarikhPjbPertama"), project.get("permitMula")):
                excluded_legacy_projects += 1
                if index == 1 or index % 10 == 0 or index == total:
                    progress(f"Reviewed {index}/{total} catalog projects (latest: {project_code}).")
                continue

            try:
                unit_result = client.project_units(project_code)
                units_payload = unit_result.payload
                retrieved_at = max(retrieved_at, unit_result.retrieved_at)
            except SourceAnomaly as exc:
                failed_units += 1
                anomalies.append(f"{project_code} units: {exc}")
            record = calculate_project_metrics(
                search_project=search_project,
                detail=detail_payload,
                units_payload=units_payload,
                city_lookup=city_lookup,
                snapshot_date=snapshot_date,
                source_dataset_as_of=source_dataset_as_of,
                retrieved_at=retrieved_at,
            )
            records.append(record)
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
    selected = select_exactly_five(records)
    paths = export_outputs(
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
