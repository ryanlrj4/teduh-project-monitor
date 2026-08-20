from __future__ import annotations

import pandas as pd

from teduh_phase2.presentation import (
    latest_project_changes,
    present_alert,
    translate_teduh_text,
)


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


def test_translate_teduh_text_translates_common_source_values() -> None:
    assert translate_teduh_text("Berfasa", english=True) == "Phased development"
    assert translate_teduh_text("Jadual H", english=True) == "Schedule H"
    assert translate_teduh_text("36 Bulan", english=True) == "36 months"
    assert translate_teduh_text("Daerah Timor Laut, Pulau Pinang", english=True) == (
        "Northeast District, Penang"
    )


def test_translate_teduh_text_preserves_malay_and_official_status_terms() -> None:
    assert translate_teduh_text("Berfasa", english=False) == "Berfasa"
    assert translate_teduh_text("Lancar", english=True) == "Lancar"
    assert translate_teduh_text("Sakit", english=True) == "Sakit"
    assert translate_teduh_text("Siap Dengan CCC", english=True) == "Siap Dengan CCC"
