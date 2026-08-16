from decimal import Decimal

from teduh_phase2.metrics import (
    calculate_project_metrics,
    ccc_obtained,
    component_completion_dates,
    duplicate_unit_count,
    indicative_gdv_range,
    teduh_spa_price_range,
    weighted_construction,
)


def project_inputs(units: list[dict], *, reported: int = 2, rows: list[dict] | None = None):
    search = {
        "id": "999-1",
        "kod_pemaju": "999",
        "nama": "Synthetic Project",
        "kod_bandar_id": "1400144",
        "pemaju": {"kod_pemaju": "999", "nama": "Synthetic Developer"},
        "status_project": {"keterangan": "Lancar"},
    }
    detail = {
        "projek": {
            "kod_projek": "999-1",
            "nama": "Synthetic Project",
            "negeri": "WP Kuala Lumpur",
            "daerah": "Kuala Lumpur",
            "permitNo": "999-1/TEST",
            "permitMula": "2026-01-01",
            "permitTamat": "2029-01-01",
        },
        "pemaju": {"kod_pemaju": "999", "nama": "Synthetic Developer"},
        "unitSummary": {"unit": reported},
        "pjb": {},
        "status": {
            "keseluruhan": "Lancar",
            "rows": rows
            or [
                {
                    "jenis": "Apartment",
                    "tingkat": "10",
                    "bilik": "3",
                    "tandas": "2",
                    "keluasan": "100",
                    "unit": reported,
                    "hargaMin": "100000",
                    "hargaMax": "200000",
                    "peratus": "50",
                }
            ],
        },
    }
    payload = {"unitGroups": [{"pembangunan_id": 1, "jenis": "Apartment", "units": units}]}
    return search, detail, payload


def test_sold_count_coverage_and_values() -> None:
    units = [
        {
            "no": "A-1",
            "status": "sold",
            "statusJualan": "Telah Dijual",
            "hargaJualan": "RM 100,000.00",
            "hargaSPJB": "RM 90,000.00",
        },
        {
            "no": "A-2",
            "status": "avail",
            "statusJualan": "Belum Dijual",
            "hargaJualan": "RM 120,000.00",
            "hargaSPJB": "-",
        },
    ]
    search, detail, payload = project_inputs(units)
    result = calculate_project_metrics(
        search_project=search,
        detail=detail,
        units_payload=payload,
        city_lookup={"1400144": "Bandar Kuala Lumpur"},
        snapshot_date="2026-08-16",
        source_dataset_as_of="2026-08-15",
        retrieved_at="2026-08-16T12:00:00+08:00",
    )
    assert result["sold_units"] == 1
    assert result["unsold_units"] == 1
    assert result["sales_percentage"] == 50.0
    assert result["unit_coverage_percentage"] == 100.0
    assert result["potential_listed_gdv"] == Decimal("220000.00")
    assert result["recorded_spa_sales_value"] == Decimal("90000.00")
    assert result["teduh_spa_price_min"] == Decimal("100000")
    assert result["teduh_spa_price_max"] == Decimal("200000")
    assert result["estimated_sold_value"] == Decimal("90000.00")
    assert result["remaining_listed_value"] == Decimal("120000.00")
    assert result["gdv_confidence"] == "high"
    assert result["sales_value_confidence"] == "high"
    assert result["construction_percentage"] == 50.0


def test_estimated_sales_uses_listed_price_when_spa_missing() -> None:
    units = [
        {
            "no": "A-1",
            "status": "sold",
            "statusJualan": "Dijual",
            "hargaJualan": "100000",
            "hargaSPJB": "-",
        }
    ]
    search, detail, payload = project_inputs(units, reported=1)
    result = calculate_project_metrics(
        search_project=search,
        detail=detail,
        units_payload=payload,
        city_lookup={},
        snapshot_date="2026-08-16",
        source_dataset_as_of="2026-08-15",
        retrieved_at="2026-08-16T12:00:00+08:00",
    )
    assert result["recorded_spa_sales_value"] is None
    assert result["estimated_sold_value"] == Decimal("100000")
    assert result["spa_price_coverage_percentage"] == 0.0


def test_absent_unit_rows_do_not_become_zero_sales_value() -> None:
    search, detail, payload = project_inputs([], reported=10)
    result = calculate_project_metrics(
        search_project=search,
        detail=detail,
        units_payload=payload,
        city_lookup={},
        snapshot_date="2026-08-16",
        source_dataset_as_of="2026-08-15",
        retrieved_at="2026-08-16T12:00:00+08:00",
    )
    assert result["sold_units"] == 0
    assert result["recorded_spa_sales_value"] is None
    assert result["estimated_sold_value"] is None
    assert result["sales_value_confidence"] == "unavailable"


def test_construction_weighting() -> None:
    rows = [
        {"jenis": "A", "tingkat": "1", "bilik": "2", "tandas": "1", "keluasan": "80", "unit": 25, "peratus": 20},
        {"jenis": "B", "tingkat": "2", "bilik": "3", "tandas": "2", "keluasan": "100", "unit": 75, "peratus": 60},
    ]
    percentage, confidence, note, row_units = weighted_construction(rows, 100)
    assert percentage == 50.0
    assert confidence == "high"
    assert note is None
    assert row_units == 100


def test_construction_reconciliation_failure_is_unavailable() -> None:
    rows = [
        {"jenis": "A", "tingkat": "1", "bilik": "2", "tandas": "1", "keluasan": "80", "unit": 25, "peratus": 20}
    ]
    percentage, confidence, note, _ = weighted_construction(rows, 100)
    assert percentage is None
    assert confidence == "unavailable"
    assert "do not reconcile" in note


def test_duplicate_detection() -> None:
    units = [
        {"pembangunan_id": 1, "no": "A-1"},
        {"pembangunan_id": 1, "no": "A-1"},
        {"pembangunan_id": 2, "no": "A-1"},
    ]
    assert duplicate_unit_count(units) == 1


def test_indicative_gdv_range() -> None:
    rows = [
        {
            "jenis": "A",
            "tingkat": "1",
            "bilik": "2",
            "tandas": "1",
            "keluasan": "80",
            "unit": 2,
            "hargaMin": "100000",
            "hargaMax": "150000",
        }
    ]
    minimum, maximum = indicative_gdv_range(rows, 2)
    assert minimum == Decimal("200000")
    assert maximum == Decimal("300000")


def test_teduh_spa_price_range_matches_component_table() -> None:
    minimum, maximum = teduh_spa_price_range(
        [
            {"hargaMin": "805,200.00", "hargaMax": "2,482,800.00"},
            {"hargaMin": "900,000.00", "hargaMax": "2,000,000.00"},
        ]
    )
    assert minimum == Decimal("805200.00")
    assert maximum == Decimal("2482800.00")


def test_ccc_obtained_is_yes_for_any_component_evidence() -> None:
    assert ccc_obtained([{"komponen": "Siap Dengan CCC", "ccc": "-"}]) == "Yes"
    assert ccc_obtained([{"komponen": "Lancar", "ccc": "27/01/2026"}]) == "Yes"
    assert ccc_obtained([], "Siap Dengan CCC") == "Yes"
    assert ccc_obtained([], "Siap Dengan CFO") == "Yes"
    assert ccc_obtained([{"komponen": "Lancar", "ccc": "-"}]) == "No"


def test_component_completion_dates_use_latest_valid_component_dates() -> None:
    assert component_completion_dates(
        [
            {"ccc": "23/02/2026", "vp": "31/03/2026"},
            {"ccc": "10/03/2026", "vp": "-"},
        ]
    ) == ("2026-03-10", "2026-03-31")
