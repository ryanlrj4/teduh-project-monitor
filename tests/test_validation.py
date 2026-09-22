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
    legacy["hims_project_reference_date"] = "2021-12-31"
    issues = validate_records([legacy])
    assert "legacy_project_in_output" in {issue["code"] for issue in issues}
