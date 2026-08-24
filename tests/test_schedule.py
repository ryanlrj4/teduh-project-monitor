from __future__ import annotations

import csv
from datetime import date

from teduh_monitor.config import Settings
from teduh_monitor.monitor import current_metrics_path
from teduh_monitor.schedule import refresh_if_due, week_start


def test_week_start_uses_monday() -> None:
    assert week_start(date(2026, 8, 16)) == date(2026, 8, 10)
    assert week_start(date(2026, 8, 17)) == date(2026, 8, 17)


def test_weekly_refresh_skips_when_current_week_exists(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    path = current_metrics_path(settings)
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snapshot_date"])
        writer.writeheader()
        writer.writerow({"snapshot_date": "2026-08-17"})

    result = refresh_if_due(
        settings,
        today=date(2026, 8, 20),
        progress=lambda _: None,
    )

    assert result["refreshed"] is False
    assert result["due_from"] == "2026-08-17"
