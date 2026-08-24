from teduh_monitor.full_catalog import select_validation_sample
from teduh_monitor.validate import validate_records


def record(code: str, status: str, reported: int, coverage: float, sold: int = 0):
    return {
        "snapshot_date": "2026-08-16",
        "source_project_id": code,
        "hims_project_reference_date": "2026-01-01",
        "ccc_obtained": "No",
        "project_status": status,
        "reported_total_units": reported,
        "unit_records_count": round(reported * coverage / 100),
        "sold_units": sold,
        "unsold_units": 0,
        "comparable_total_units": max(sold, 1),
        "unit_coverage_percentage": coverage,
        "listed_price_coverage_percentage": coverage,
        "sales_percentage": 0.0,
        "construction_percentage": None,
        "duplicate_unit_identifiers": 0,
        "unknown_sales_status_units": 0,
        "construction_note": "No construction rows",
    }


def test_exactly_five_selection() -> None:
    records = [
        record("A-1", "Belum Mula", 100, 100),
        record("B-1", "Lancar", 200, 100, sold=50),
        record("C-1", "Lancar", 300, 10),
        record("D-1", "Lewat", 400, 80),
        record("E-1", "Sakit", 500, 70),
    ]
    selected = select_validation_sample(records)
    assert len(selected) == 5
    assert [role for role, _ in selected] == [
        "not_started",
        "active_data_rich",
        "active_mid_sales",
        "delayed",
        "sick",
    ]
    assert len({row["source_project_id"] for _, row in selected}) == 5


def test_validation_detects_duplicate_projects_and_bad_percentage() -> None:
    first = record("A-1", "Lancar", 10, 100)
    second = dict(first)
    second["sales_percentage"] = 101
    issues = validate_records([first, second])
    codes = {issue["code"] for issue in issues}
    assert "duplicate_project" in codes
    assert "percentage_out_of_range" in codes


def test_validation_rejects_legacy_project() -> None:
    legacy = record("OLD-1", "Lancar", 10, 100)
    legacy["hims_project_reference_date"] = "2022-01-30"
    issues = validate_records([legacy])
    assert "legacy_project_in_output" in {issue["code"] for issue in issues}
