from teduh_phase2.ui.formatting import (
    display_duration,
    json_rows,
    money,
    numeric_range,
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
