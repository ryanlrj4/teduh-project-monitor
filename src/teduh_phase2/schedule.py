from __future__ import annotations

import csv
from datetime import date, timedelta
from typing import Any, Callable

from .config import Settings
from .monitor import current_metrics_path, snapshot_shortlist


Progress = Callable[[str], None]


def week_start(day: date) -> date:
    """Return the Monday for the week containing ``day``."""
    return day - timedelta(days=day.weekday())


def latest_observation_date(settings: Settings) -> date | None:
    path = current_metrics_path(settings)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        dates = {
            row.get("snapshot_date", "")
            for row in csv.DictReader(handle)
            if row.get("snapshot_date")
        }
    parsed: list[date] = []
    for value in dates:
        try:
            parsed.append(date.fromisoformat(value))
        except ValueError:
            continue
    return max(parsed, default=None)


def refresh_if_due(
    settings: Settings,
    *,
    today: date | None = None,
    progress: Progress = print,
) -> dict[str, Any]:
    """Refresh once per Monday-based week when invoked by an external scheduler."""
    current_day = today or date.today()
    due_from = week_start(current_day)
    latest = latest_observation_date(settings)
    if latest is not None and latest >= due_from:
        progress(f"Weekly TEDUH refresh is current through {latest.isoformat()}.")
        return {
            "refreshed": False,
            "due_from": due_from.isoformat(),
            "latest_observation": latest.isoformat(),
        }
    progress(f"Weekly TEDUH refresh is due for the week of {due_from.isoformat()}.")
    result = snapshot_shortlist(settings, progress=progress)
    return {
        "refreshed": True,
        "due_from": due_from.isoformat(),
        "latest_observation": result["snapshot_date"],
        "project_count": result["project_count"],
        "alert_count": result["alert_count"],
    }
