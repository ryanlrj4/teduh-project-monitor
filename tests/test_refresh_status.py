from __future__ import annotations

from teduh_phase2.config import Settings
from teduh_phase2.refresh_status import (
    complete_refresh_failure,
    complete_refresh_success,
    load_refresh_history,
    load_refresh_status,
    start_refresh,
    update_refresh,
)


def test_successful_refresh_status_is_persisted(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    start_refresh(settings, trigger="manual", total_projects=3)
    update_refresh(
        settings,
        completed_projects=1,
        successful_projects=1,
        failed_projects=0,
        current_project_code="100-1",
    )
    complete_refresh_success(
        settings,
        result={
            "snapshot_date": "2026-08-19",
            "source_dataset_as_of": "2026-08-18",
            "project_count": 3,
            "cached_project_count": 2,
            "live_project_count": 1,
            "alert_count": 4,
        },
    )
    status = load_refresh_status(settings)
    assert status["status"] == "success"
    assert status["publication_status"] == "Published after validation"
    assert status["cached_projects"] == 2
    assert status["last_successful_snapshot_date"] == "2026-08-19"
    assert len(load_refresh_history(settings)) == 1


def test_failed_refresh_preserves_last_successful_metadata(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    start_refresh(settings, trigger="manual", total_projects=1)
    complete_refresh_success(
        settings,
        result={
            "snapshot_date": "2026-08-18",
            "source_dataset_as_of": "2026-08-17",
            "project_count": 1,
            "cached_project_count": 0,
            "live_project_count": 1,
            "alert_count": 0,
        },
    )
    start_refresh(settings, trigger="scheduled", total_projects=1)
    complete_refresh_failure(settings, error=RuntimeError("TEDUH unavailable"))
    status = load_refresh_status(settings)
    assert status["status"] == "failed"
    assert status["previous_snapshot_preserved"] is True
    assert status["last_successful_snapshot_date"] == "2026-08-18"
    assert "TEDUH unavailable" in status["error"]
    assert len(load_refresh_history(settings)) == 2
