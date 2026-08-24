from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import calculate_project_metrics
from .normalize import is_hims_eligible, normalize_state
from .sources import SourceAnomaly, TeduhClient


class IneligibleProject(ValueError):
    """Raised when a project predates comparable HIMS coverage."""


@dataclass(frozen=True)
class CollectedProject:
    record: dict[str, Any]
    detail_from_cache: bool
    units_from_cache: bool | None
    unit_error: SourceAnomaly | None


def search_project_from_detail(
    project_code: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    project = detail.get("projek") or {}
    developer = detail.get("pemaju") or {}
    status = detail.get("status") or {}
    return {
        "id": project_code,
        "nama": detail.get("nama") or project.get("nama"),
        "kod_pemaju": developer.get("kod_pemaju"),
        "latest_lesen": developer.get("latest_lesen") or {},
        "status_project": {"keterangan": status.get("keseluruhan")},
    }


def collect_project(
    client: TeduhClient,
    *,
    project_code: str,
    snapshot_date: str,
    source_dataset_as_of: str,
    search_project: dict[str, Any] | None = None,
    city_lookup: dict[str, str] | None = None,
    expected_state: str | None = None,
    expected_region: str | None = None,
    allow_missing_units: bool = False,
) -> CollectedProject:
    detail_result = client.project_detail(project_code)
    detail = detail_result.payload
    project = detail.get("projek") or {}
    pjb = detail.get("pjb") or {}

    if expected_state is not None:
        observed_state = normalize_state(project.get("negeri"))
        if observed_state != expected_state:
            raise SourceAnomaly(
                f"{project_code} is registered in {observed_state or 'an unknown state'}, "
                f"not the selected {expected_region or expected_state} region"
            )

    if not is_hims_eligible(pjb.get("tarikhPjbPertama"), project.get("permitMula")):
        raise IneligibleProject(f"{project_code} predates comparable HIMS coverage")

    units_payload: dict[str, Any] | None = None
    units_from_cache: bool | None = None
    unit_error: SourceAnomaly | None = None
    retrieved_at = detail_result.retrieved_at
    try:
        unit_result = client.project_units(project_code)
        units_payload = unit_result.payload
        units_from_cache = unit_result.from_cache
        retrieved_at = max(retrieved_at, unit_result.retrieved_at)
    except SourceAnomaly as exc:
        if not allow_missing_units:
            raise
        unit_error = exc

    record = calculate_project_metrics(
        search_project=(
            search_project
            if search_project is not None
            else search_project_from_detail(project_code, detail)
        ),
        detail=detail,
        units_payload=units_payload,
        city_lookup=city_lookup or {},
        snapshot_date=snapshot_date,
        source_dataset_as_of=source_dataset_as_of,
        retrieved_at=retrieved_at,
    )
    return CollectedProject(
        record=record,
        detail_from_cache=detail_result.from_cache,
        units_from_cache=units_from_cache,
        unit_error=unit_error,
    )
