from decimal import Decimal

from teduh_monitor.normalize import (
    hims_project_reference,
    is_hims_eligible,
    normalize_sales_status,
    parse_date,
    parse_price,
    safe_percentage,
)


def test_price_parsing() -> None:
    assert parse_price("RM 2,340,333.00") == Decimal("2340333.00")
    assert parse_price("-") is None
    assert parse_price(None) is None
    assert parse_price("(1,250.50)") == Decimal("-1250.50")


def test_date_parsing() -> None:
    assert parse_date("2026-04-10").isoformat() == "2026-04-10"
    assert parse_date("09/04/2029").isoformat() == "2029-04-09"
    assert parse_date("-") is None
    assert parse_date("not a date") is None


def test_sales_status_normalization() -> None:
    assert normalize_sales_status("Telah Dijual", "sold") == "sold"
    assert normalize_sales_status("Belum Dijual", "avail") == "unsold"
    assert normalize_sales_status("Tempahan") == "booked"
    assert normalize_sales_status("nilai baharu") == "unknown"
    assert normalize_sales_status(None, "available") == "unsold"


def test_safe_percentage() -> None:
    assert safe_percentage(1, 4) == 25.0
    assert safe_percentage(1, 0) is None
    assert safe_percentage(1, None) is None


def test_hims_reference_prefers_first_spa_over_renewed_permit() -> None:
    reference, basis = hims_project_reference("16 Dec 2021", "2025-12-08")
    assert reference == "2021-12-16"
    assert basis == "first_spa_date"
    assert not is_hims_eligible("16 Dec 2021", "2025-12-08")


def test_hims_reference_falls_back_to_permit_for_project_without_spa() -> None:
    reference, basis = hims_project_reference("-", "2022-01-31")
    assert reference == "2022-01-31"
    assert basis == "permit_start_date_fallback"
    assert is_hims_eligible("-", "2022-01-31")
