from __future__ import annotations

import pandas as pd

from teduh_phase2.presentation import latest_project_changes, present_alert


def test_latest_project_changes_only_returns_changed_projects() -> None:
    current = pd.DataFrame(
        [
            {
                "snapshot_date": "2026-08-19",
                "source_project_id": "1-1",
                "display_name": "Changed",
                "region": "Kuala Lumpur",
                "project_status": "Lancar",
                "sold_units": 101,
                "sales_percentage": 50.5,
                "construction_percentage": 25.0,
            },
            {
                "snapshot_date": "2026-08-19",
                "source_project_id": "2-1",
                "display_name": "Unchanged",
                "region": "Penang",
                "project_status": "Lancar",
                "sold_units": 40,
                "sales_percentage": 40.0,
                "construction_percentage": 10.0,
            },
        ]
    )
    history = pd.DataFrame(
        [
            {
                "snapshot_date": "2026-08-16",
                "source_project_id": "1-1",
                "project_status": "Lancar",
                "sold_units": 100,
                "sales_percentage": 50.0,
                "construction_percentage": 25.0,
            },
            {
                "snapshot_date": "2026-08-16",
                "source_project_id": "2-1",
                "project_status": "Lancar",
                "sold_units": 40,
                "sales_percentage": 40.0,
                "construction_percentage": 10.0,
            },
        ]
    )

    changes = latest_project_changes(current, history)

    assert changes["source_project_id"].tolist() == ["1-1"]
    assert changes.iloc[0]["sold_units_delta"] == 1
    assert changes.iloc[0]["sales_percentage_delta"] == 0.5
    assert changes.iloc[0]["construction_percentage_delta"] == 0


def test_present_alert_uses_business_facing_level_and_category() -> None:
    alert = present_alert(
        {
            "alert_code": "sold_units_decreased",
            "severity": "high",
            "message": "Reported sold units decreased from 100 to 99",
        }
    )

    assert alert["alert_label"] == "Reported sold units decreased"
    assert alert["alert_category"] == "Source revision"
    assert alert["alert_level"] == "Review"
