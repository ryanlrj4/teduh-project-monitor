from decimal import Decimal

import pytest

from teduh_phase2.storage import (
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
    parquet_row_count,
    read_csv,
    read_json,
)


def test_atomic_csv_round_trip_preserves_schema_and_decimal_text(tmp_path) -> None:
    path = tmp_path / "nested" / "rows.csv"

    atomic_write_csv(
        path,
        [{"code": "100-1", "amount": Decimal("123.40"), "ignored": "value"}],
        ["code", "amount", "missing"],
    )

    assert read_csv(path) == [
        {"code": "100-1", "amount": "123.40", "missing": ""}
    ]
    assert not path.with_suffix(".csv.tmp").exists()


def test_atomic_json_round_trip_and_invalid_fallback(tmp_path) -> None:
    path = tmp_path / "nested" / "status.json"
    atomic_write_json(path, {"status": "success", "project": "M Área"})

    assert read_json(path, {}) == {"status": "success", "project": "M Área"}
    path.write_text("not-json", encoding="utf-8")
    assert read_json(path, {"status": "unknown"}) == {"status": "unknown"}
    with pytest.raises(ValueError):
        read_json(path, {}, tolerate_invalid=False)


def test_atomic_parquet_uses_declared_schema_and_expected_row_count(tmp_path) -> None:
    path = tmp_path / "nested" / "metrics.parquet"
    specs = [("code", "VARCHAR"), ("units", "BIGINT"), ("sales", "DOUBLE")]

    atomic_write_parquet(
        path,
        [{"code": "100-1", "units": "42", "sales": "6.9"}],
        specs,
        blank_as_none=True,
    )

    assert parquet_row_count(path) == 1
    assert not path.with_suffix(".parquet.tmp").exists()
