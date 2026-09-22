from teduh_monitor.ui.formatting import (
    display_date,
    display_duration,
    json_rows,
    money,
    numeric_range,
    project_choice_label,
    signed_number,
)


def test_money_and_numeric_range_use_business_display_format() -> None:
    assert money("1234567.8") == "RM 1,234,568"
    assert numeric_range("500000", "750000", prefix="RM ") == "RM 500,000–750,000"
    assert numeric_range("500000", "500000", prefix="RM ") == "RM 500,000"


def test_signed_number_and_duration_handle_common_display_cases() -> None:
    assert signed_number(0, zero_label="No change") == "No change"
    assert signed_number(2.5, decimals=1, suffix=" pp") == "+2.5 pp"
    assert display_duration(65) == "1 min 05 sec"


def test_json_rows_accepts_only_lists_of_objects() -> None:
    assert json_rows('[{"component": 1}, "invalid"]') == [{"component": 1}]
    assert json_rows('{"component": 1}') == []
    assert json_rows("not-json") == []


def test_display_date_supports_api_and_teduh_display_formats() -> None:
    assert display_date("2026-08-25") == "25 Aug 2026"
    assert display_date("25/08/2026") == "25 Aug 2026"
    assert display_date("not-a-date") == "N/A"


def test_project_choice_label_is_searchable_by_name_code_and_group() -> None:
    assert project_choice_label(
        {
            "source_project_id": "100-1",
            "display_name": "Local Project",
            "project_name": "Registered Project",
            "parent_group": "Example Group",
            "developer_name": "EXAMPLE PROJECT SDN. BHD.",
        }
    ) == (
        "Local Project · 100-1 · Example Group · EXAMPLE PROJECT SDN. BHD."
    )
