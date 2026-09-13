from __future__ import annotations

from pathlib import Path

import pytest

from teduh_monitor.config import Settings
from teduh_monitor.monitor import (
    alerts_path,
    current_metrics_path,
    history_csv_path,
    refresh_projects,
)
from teduh_monitor.schema import ALERT_FIELDS, SHORTLIST_FIELDS
from teduh_monitor.shortlist import upsert_shortlist_project
from teduh_monitor.sources import SourceAnomaly, SourceResult
from teduh_monitor.storage import atomic_write_csv, read_csv


def _source_result(payload: dict, *, project_code: str) -> SourceResult:
    return SourceResult(
        payload=payload,
        retrieved_at="2026-09-14T10:00:00+08:00",
        url=f"https://teduh.example/api/{project_code}",
        cache_path=Path(f"{project_code}.json"),
        from_cache=False,
    )


class FakeTeduhClient:
    constructed = 0

    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_date: str,
        force: bool,
    ) -> None:
        type(self).constructed += 1
        self.snapshot_date = snapshot_date

    def __enter__(self) -> "FakeTeduhClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def project_detail(self, project_code: str) -> SourceResult:
        return _source_result(
            {
                "nama": f"Project {project_code}",
                "projek": {
                    "kod_projek": project_code,
                    "nama": f"Project {project_code}",
                    "negeri": "WP Kuala Lumpur",
                    "permitMula": "2025-01-01",
                },
                "pemaju": {
                    "kod_pemaju": project_code.split("-")[0],
                    "nama": "Synthetic Developer",
                    "latest_lesen": {},
                },
                "unitSummary": {"unit": 1},
                "pjb": {"tarikhPjbPertama": "2026-01-01"},
                "status": {"keseluruhan": "Lancar", "rows": []},
            },
            project_code=project_code,
        )

    def project_units(self, project_code: str) -> SourceResult:
        return _source_result(
            {
                "unitGroups": [
                    {
                        "pembangunan_id": 1,
                        "jenis": "Apartment",
                        "units": [
                            {
                                "no": "A-1",
                                "status": "sold",
                                "statusJualan": "Telah Dijual",
                                "hargaJualan": "100000",
                                "hargaSPJB": "90000",
                            }
                        ],
                    }
                ]
            },
            project_code=project_code,
        )


class FailingTeduhClient(FakeTeduhClient):
    def project_detail(self, project_code: str) -> SourceResult:
        raise SourceAnomaly("synthetic source failure")


def _tracked_project(settings: Settings, project_code: str) -> None:
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": project_code,
            "region": "Kuala Lumpur",
            "display_name": f"Tracked {project_code}",
            "project_set": "general",
            "active": "Yes",
        },
        changed_by="TEST",
    )


def _stored_record(project_code: str, snapshot_date: str) -> dict[str, object]:
    return {
        "region": "Kuala Lumpur",
        "display_name": f"Tracked {project_code}",
        "project_set": "general",
        "shortlist_active": "Yes",
        "snapshot_date": snapshot_date,
        "source": "TEDUH",
        "source_project_id": project_code,
        "project_name": f"Project {project_code}",
        "hims_project_reference_date": "2026-01-01",
        "hims_eligibility_cutoff_date": "2022-01-31",
        "project_status": "Lancar",
        "ccc_obtained": "No",
        "reported_total_units": 1,
        "unit_records_count": 1,
        "sold_units": 0,
        "unsold_units": 1,
        "comparable_total_units": 1,
    }


def _seed_outputs(
    settings: Settings,
    current: list[dict[str, object]],
    history: list[dict[str, object]],
) -> None:
    atomic_write_csv(current_metrics_path(settings), current, SHORTLIST_FIELDS)
    atomic_write_csv(history_csv_path(settings), history, SHORTLIST_FIELDS)
    atomic_write_csv(alerts_path(settings), [], ALERT_FIELDS)


def test_selected_refresh_replaces_only_target_and_appends_observation(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    _tracked_project(settings, "100-1")
    _tracked_project(settings, "200-1")
    first = _stored_record("100-1", "2026-09-13")
    second = _stored_record("200-1", "2026-09-13")
    _seed_outputs(settings, [first, second], [first, second])

    result = refresh_projects(
        settings,
        ["100-1"],
        snapshot_date="2026-09-14",
        progress=lambda _: None,
        client_factory=FakeTeduhClient,
    )

    current = {row["source_project_id"]: row for row in read_csv(current_metrics_path(settings))}
    history = read_csv(history_csv_path(settings))
    assert result["project_count"] == 1
    assert result["skipped_same_day_count"] == 0
    assert current["100-1"]["snapshot_date"] == "2026-09-14"
    assert current["100-1"]["sold_units"] == "1"
    assert current["200-1"]["snapshot_date"] == "2026-09-13"
    assert len(history) == 3
    assert {
        (row["source_project_id"], row["snapshot_date"]) for row in history
    } == {
        ("100-1", "2026-09-13"),
        ("100-1", "2026-09-14"),
        ("200-1", "2026-09-13"),
    }


def test_selected_refresh_skips_project_already_observed_today(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    _tracked_project(settings, "100-1")
    current = [_stored_record("100-1", "2026-09-14")]
    _seed_outputs(settings, current, current)
    FakeTeduhClient.constructed = 0

    result = refresh_projects(
        settings,
        ["100-1"],
        snapshot_date="2026-09-14",
        progress=lambda _: None,
        client_factory=FakeTeduhClient,
    )

    assert result["project_count"] == 0
    assert result["skipped_same_day_count"] == 1
    assert FakeTeduhClient.constructed == 0


def test_selected_refresh_fetches_only_stale_projects_in_mixed_request(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    _tracked_project(settings, "100-1")
    _tracked_project(settings, "200-1")
    current_today = _stored_record("100-1", "2026-09-14")
    current_stale = _stored_record("200-1", "2026-09-13")
    _seed_outputs(
        settings,
        [current_today, current_stale],
        [current_today, current_stale],
    )

    result = refresh_projects(
        settings,
        ["100-1", "200-1"],
        snapshot_date="2026-09-14",
        progress=lambda _: None,
        client_factory=FakeTeduhClient,
    )

    current = {
        row["source_project_id"]: row
        for row in read_csv(current_metrics_path(settings))
    }
    assert result["refreshed_project_codes"] == ["200-1"]
    assert result["skipped_project_codes"] == ["100-1"]
    assert current["100-1"]["snapshot_date"] == "2026-09-14"
    assert current["200-1"]["snapshot_date"] == "2026-09-14"


def test_selected_refresh_preserves_outputs_when_teduh_fails(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    _tracked_project(settings, "100-1")
    current = [_stored_record("100-1", "2026-09-13")]
    _seed_outputs(settings, current, current)
    current_before = current_metrics_path(settings).read_bytes()
    history_before = history_csv_path(settings).read_bytes()
    alerts_before = alerts_path(settings).read_bytes()

    with pytest.raises(SourceAnomaly, match="valid outputs were preserved"):
        refresh_projects(
            settings,
            ["100-1"],
            snapshot_date="2026-09-14",
            progress=lambda _: None,
            client_factory=FailingTeduhClient,
        )

    assert current_metrics_path(settings).read_bytes() == current_before
    assert history_csv_path(settings).read_bytes() == history_before
    assert alerts_path(settings).read_bytes() == alerts_before
