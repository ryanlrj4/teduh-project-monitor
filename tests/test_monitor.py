from __future__ import annotations

from decimal import Decimal

from teduh_monitor.monitor import build_alerts, project_scale
from teduh_monitor.config import REGION_CONFIGS


def test_project_scale_keeps_unknown_projects_for_review() -> None:
    assert project_scale(None, "unavailable")[1] == "Review"
    assert project_scale(Decimal("49999999"), "high")[1] == "Below floor"
    assert project_scale(Decimal("50000000"), "high")[1] == "Include"
    assert project_scale(Decimal("1000000000"), "high")[0] == "RM1bn+"


def test_region_state_mapping_covers_pilot_regions() -> None:
    assert REGION_CONFIGS["Kuala Lumpur"]["state_label"] == "Wp Kuala Lumpur"
    assert REGION_CONFIGS["Penang"]["state_label"] == "Pulau Pinang"
    assert REGION_CONFIGS["Selangor"]["state_id"] == "10"
    assert REGION_CONFIGS["Johor"]["state_id"] == "01"
    assert REGION_CONFIGS["Malacca"]["state_label"] == "Melaka"


def test_alerts_flag_risk_and_negative_changes() -> None:
    history = [
        {
            "snapshot_date": "2026-08-15",
            "source_project_id": "1-1",
            "display_name": "Example",
            "project_status": "Lancar",
            "sold_units": "100",
            "construction_percentage": "40",
            "ccc_obtained": "No",
            "construction_confidence": "high",
        },
        {
            "snapshot_date": "2026-08-16",
            "source_project_id": "1-1",
            "display_name": "Example",
            "project_status": "Sakit",
            "sold_units": "98",
            "construction_percentage": "35",
            "ccc_obtained": "Yes",
            "construction_confidence": "high",
        },
    ]
    codes = {alert["alert_code"] for alert in build_alerts(history)}
    assert {
        "status_sakit",
        "status_changed",
        "sold_units_decreased",
        "construction_decreased",
        "completion_certificate_obtained",
    }.issubset(codes)


def test_alerts_surface_permit_developer_and_sales_gap_exceptions() -> None:
    history = [
        {
            "snapshot_date": "2026-09-13",
            "source_project_id": "1-1",
            "display_name": "Example",
            "project_status": "Lancar",
            "construction_confidence": "high",
            "permit_end_date": "2026-09-01",
            "developer_license_end_date": "2026-10-01",
            "developer_status": "Tidak Aktif",
            "sales_construction_gap": "-30",
        }
    ]
    codes = {alert["alert_code"] for alert in build_alerts(history)}
    assert {
        "permit_expired",
        "developer_licence_expiring",
        "developer_inactive",
        "sales_lags_construction",
    }.issubset(codes)
