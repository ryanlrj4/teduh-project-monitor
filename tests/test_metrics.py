from decimal import Decimal
from statistics import median

import pytest

from teduh_monitor.metrics import (
    calculate_project_metrics,
    ccc_obtained,
    component_sales_summary,
    component_completion_dates,
    duplicate_unit_count,
    indicative_gdv_range,
    price_percentile,
    remaining_inventory_summary,
    teduh_spa_price_range,
    weighted_construction,
)


def test_component_sales_are_calculated_per_teduh_unit_group() -> None:
    payload = {
        "unitGroups": [
            {
                "pembangunan_id": 101,
                "jenis": "Apartment",
                "units": [
                    {"no": "A-1", "statusJualan": "Telah Dijual", "status": "sold"},
                    {"no": "A-2", "statusJualan": "Belum Dijual", "status": "avail"},
                ],
            },
            {
                "pembangunan_id": 102,
                "jenis": "Soho",
                "units": [
                    {"no": "B-1", "statusJualan": "Telah Dijual", "status": "sold"},
                    {"no": "B-2", "statusJualan": "Telah Dijual", "status": "sold"},
                ],
            },
        ]
    }
    rows, confidence, note = component_sales_summary(payload, 4)
    assert confidence == "high"
    assert note is None
    assert [row["component_label"] for row in rows] == ["Component 1", "Component 2"]
    assert rows[0]["source_component_id"] == "101"
    assert rows[0]["sales_percentage"] == 50.0
    assert rows[1]["sales_percentage"] == 100.0


def test_component_sales_report_reconciliation_problem() -> None:
    payload = {
        "unitGroups": [
            {
                "pembangunan_id": 101,
                "jenis": "Apartment",
                "units": [{"no": "A-1", "statusJualan": "Telah Dijual", "status": "sold"}],
            }
        ]
    }
    _, confidence, note = component_sales_summary(payload, 2)
    assert confidence == "low"
    assert "do not reconcile" in str(note)


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
    assert result["value_sold_percentage"] == pytest.approx(40.909091)
    assert result["sales_construction_gap"] == 0.0
    assert result["unit_coverage_percentage"] == 100.0
    assert result["potential_listed_gdv"] == Decimal("220000.00")
    assert result["average_listed_price_per_unit"] == Decimal("110000.00")
    assert result["median_listed_price_per_unit"] == Decimal("110000.00")
    assert result["listed_price_p25"] == Decimal("105000.000")
    assert result["listed_price_p75"] == Decimal("115000.000")
    assert result["sold_listed_value"] == Decimal("100000.00")
    assert result["recorded_spa_sales_value"] == Decimal("90000.00")
    assert result["average_recorded_spa_price_per_unit"] == Decimal("90000.00")
    assert result["median_recorded_spa_price_per_unit"] == Decimal("90000.00")
    assert result["teduh_spa_price_min"] == Decimal("100000")
    assert result["teduh_spa_price_max"] == Decimal("200000")
    assert result["estimated_sold_value"] == Decimal("90000.00")
    assert result["remaining_listed_value"] == Decimal("120000.00")
    assert result["gdv_confidence"] == "high"
    assert result["sales_value_confidence"] == "high"
    assert result["construction_percentage"] == 50.0
    assert result["recorded_price_realisation_percentage"] == 90.0
    assert result["median_recorded_discount_percentage"] == 10.0


def test_price_percentiles_keep_extremes_out_of_the_typical_price() -> None:
    prices = [
        Decimal("100000"),
        Decimal("105000"),
        Decimal("110000"),
        Decimal("115000"),
        Decimal("1000000"),
    ]

    assert median(prices) == Decimal("110000")
    assert price_percentile(prices, 0.25) == Decimal("105000")
    assert price_percentile(prices, 0.75) == Decimal("115000")


def test_zero_prices_are_not_treated_as_valid_unit_prices() -> None:
    units = [
        {
            "no": "A-1",
            "status": "sold",
            "statusJualan": "Telah Dijual",
            "hargaJualan": "100000",
            "hargaSPJB": "0",
        },
        {
            "no": "A-2",
            "status": "avail",
            "statusJualan": "Belum Dijual",
            "hargaJualan": "0",
        },
    ]
    search, detail, payload = project_inputs(units)

    result = calculate_project_metrics(
        search_project=search,
        detail=detail,
        units_payload=payload,
        city_lookup={},
        snapshot_date="2026-08-16",
        source_dataset_as_of="2026-08-15",
        retrieved_at="2026-08-16T12:00:00+08:00",
    )

    assert result["priced_unit_records_count"] == 1
    assert result["median_listed_price_per_unit"] == Decimal("100000")
    assert result["spa_price_coverage_percentage"] == 0


def test_remaining_inventory_groups_type_and_quota() -> None:
    units = [
        {"pembangunan_id": 1, "group_jenis": "Apartment", "kuotaBumi": "Ya", "hargaJualan": "100000"},
        {"pembangunan_id": 1, "group_jenis": "Apartment", "kuotaBumi": "Ya", "hargaJualan": "110000"},
        {"pembangunan_id": 1, "group_jenis": "Apartment", "kuotaBumi": "Tidak", "hargaJualan": "120000"},
    ]
    rows = remaining_inventory_summary(units, ["unsold", "booked", "sold"])
    assert len(rows) == 1
    assert rows[0]["quota_category"] == "Bumiputera"
    assert rows[0]["units"] == 2
    assert rows[0]["listed_value"] == Decimal("210000")


def test_project_metadata_preserves_teduh_contract_and_licence_fields() -> None:
    units = [
        {
            "no": "A-1",
            "status": "sold",
            "statusJualan": "Telah Dijual",
            "hargaJualan": "100000",
            "hargaSPJB": "90000",
        }
    ]
    search, detail, payload = project_inputs(units, reported=1)
    detail.update({"lokasi": "Kuala Lumpur", "lat": "3.14", "lng": "101.70"})
    detail["pemaju"].update(
        {
            "statusPemaju": "Aktif",
            "bilanganProjek": 2,
            "latest_lesen": {
                "no_lesenpermit": "999/TEST",
                "tarikh_mula": "2024-01-01",
                "tarikh_luput": "2029-01-01",
            },
        }
    )
    detail["pjb"] = {
        "jenis": "Jadual H",
        "tempohAsal": "36 Bulan",
        "tarikhPjbPertama": "2026-02-01",
        "serahKosongIkutPjb": "2029-02-01",
        "pindaanTempohSerahKosong": "Ya",
        "tempohTambahanDiluluskan": "12 Bulan",
        "tempohPembinaanBaharu": "48 Bulan",
        "serahKosongBaharuIkutPjbPertama": "2030-02-01",
    }
    detail["status"]["maklumatPembangunan"] = "Berfasa"
    detail["lesen_records"] = [{"no_lesenpermit": "999/OLD"}]
    result = calculate_project_metrics(
        search_project=search,
        detail=detail,
        units_payload=payload,
        city_lookup={},
        snapshot_date="2026-08-19",
        source_dataset_as_of="2026-08-18",
        retrieved_at="2026-08-19T12:00:00+08:00",
    )
    assert result["developer_status"] == "Aktif"
    assert result["developer_license_number"] == "999/TEST"
    assert result["development_type"] == "Berfasa"
    assert result["agreement_type"] == "Jadual H"
    assert result["approved_extension_period"] == "12 Bulan"
    assert result["latitude"] == 3.14
    assert result["component_sales_count"] == 1
    assert "999/OLD" in result["permit_history_json"]


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
