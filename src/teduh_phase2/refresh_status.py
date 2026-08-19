from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import Settings


MAX_REFRESH_HISTORY = 10


def refresh_status_path(settings: Settings) -> Path:
    return settings.processed_dir / "refresh_status.json"


def refresh_history_path(settings: Settings) -> Path:
    return settings.processed_dir / "refresh_runs.json"


def _now() -> datetime:
    return datetime.now().astimezone()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _atomic_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_refresh_status(settings: Settings) -> dict[str, Any]:
    payload = _read_json(refresh_status_path(settings), {})
    return payload if isinstance(payload, dict) else {}


def load_refresh_history(settings: Settings) -> list[dict[str, Any]]:
    payload = _read_json(refresh_history_path(settings), [])
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def start_refresh(settings: Settings, *, trigger: str, total_projects: int) -> dict[str, Any]:
    previous = load_refresh_status(settings)
    started = _now()
    status = {
        "run_id": uuid4().hex,
        "status": "running",
        "trigger": trigger,
        "started_at": started.isoformat(timespec="seconds"),
        "completed_at": None,
        "duration_seconds": None,
        "total_projects": total_projects,
        "completed_projects": 0,
        "successful_projects": 0,
        "failed_projects": 0,
        "current_project_code": None,
        "snapshot_date": None,
        "source_dataset_as_of": None,
        "cached_projects": None,
        "live_projects": None,
        "alert_count": None,
        "publication_status": "Not yet published",
        "previous_snapshot_preserved": None,
        "error": None,
        "last_successful_completed_at": previous.get("last_successful_completed_at"),
        "last_successful_snapshot_date": previous.get("last_successful_snapshot_date"),
        "last_successful_source_dataset_as_of": previous.get(
            "last_successful_source_dataset_as_of"
        ),
    }
    _atomic_json(refresh_status_path(settings), status)
    return status


def update_refresh(
    settings: Settings,
    *,
    completed_projects: int,
    successful_projects: int,
    failed_projects: int,
    current_project_code: str,
) -> dict[str, Any]:
    status = load_refresh_status(settings)
    if status.get("status") != "running":
        return status
    status.update(
        {
            "completed_projects": completed_projects,
            "successful_projects": successful_projects,
            "failed_projects": failed_projects,
            "current_project_code": current_project_code,
        }
    )
    _atomic_json(refresh_status_path(settings), status)
    return status


def _complete_run(settings: Settings, status: dict[str, Any]) -> dict[str, Any]:
    completed = _now()
    try:
        started = datetime.fromisoformat(str(status.get("started_at") or ""))
        duration = max((completed - started).total_seconds(), 0.0)
    except ValueError:
        duration = None
    status["completed_at"] = completed.isoformat(timespec="seconds")
    status["duration_seconds"] = round(duration, 3) if duration is not None else None
    status["current_project_code"] = None
    _atomic_json(refresh_status_path(settings), status)
    history = load_refresh_history(settings)
    history.insert(0, dict(status))
    _atomic_json(refresh_history_path(settings), history[:MAX_REFRESH_HISTORY])
    return status


def complete_refresh_success(
    settings: Settings,
    *,
    result: dict[str, Any],
) -> dict[str, Any]:
    status = load_refresh_status(settings)
    status.update(
        {
            "status": "success",
            "completed_projects": result.get("project_count", status.get("completed_projects", 0)),
            "successful_projects": result.get("project_count", status.get("successful_projects", 0)),
            "failed_projects": 0,
            "snapshot_date": result.get("snapshot_date"),
            "source_dataset_as_of": result.get("source_dataset_as_of"),
            "cached_projects": result.get("cached_project_count"),
            "live_projects": result.get("live_project_count"),
            "alert_count": result.get("alert_count"),
            "publication_status": "Published after validation",
            "previous_snapshot_preserved": False,
            "error": None,
        }
    )
    status["last_successful_completed_at"] = _now().isoformat(timespec="seconds")
    status["last_successful_snapshot_date"] = result.get("snapshot_date")
    status["last_successful_source_dataset_as_of"] = result.get("source_dataset_as_of")
    return _complete_run(settings, status)


def complete_refresh_failure(settings: Settings, *, error: Exception) -> dict[str, Any]:
    status = load_refresh_status(settings)
    status.update(
        {
            "status": "failed",
            "publication_status": "Not published",
            "previous_snapshot_preserved": True,
            "error": str(error),
        }
    )
    return _complete_run(settings, status)
