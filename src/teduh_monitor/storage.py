from __future__ import annotations

import csv
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})
    return path


def atomic_write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> Path:
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_csv(temporary, rows, fields)
    os.replace(temporary, path)
    return path


def read_json(
    path: Path,
    default: Any,
    *,
    tolerate_invalid: bool = True,
) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        if tolerate_invalid:
            return default
        raise


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=ensure_ascii, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return path


def write_parquet(
    path: Path,
    rows: list[dict[str, Any]],
    field_specs: list[tuple[str, str]],
    *,
    blank_as_none: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [name for name, _ in field_specs]
    connection = duckdb.connect(":memory:")
    try:
        columns_sql = ", ".join(
            f'"{name}" {sql_type}' for name, sql_type in field_specs
        )
        connection.execute(f"CREATE TABLE metrics ({columns_sql})")
        if rows:
            placeholders = ",".join("?" for _ in fields)
            values = [
                [
                    None if blank_as_none and row.get(field) in (None, "") else row.get(field)
                    for field in fields
                ]
                for row in rows
            ]
            connection.executemany(
                f"INSERT INTO metrics VALUES ({placeholders})",
                values,
            )
        escaped = str(path.resolve()).replace("'", "''")
        connection.execute(
            f"COPY metrics TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        count = connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        if count != len(rows):
            raise RuntimeError(
                f"Parquet row count {count} does not match expected count {len(rows)}"
            )
    finally:
        connection.close()
    return path


def atomic_write_parquet(
    path: Path,
    rows: list[dict[str, Any]],
    field_specs: list[tuple[str, str]],
    *,
    blank_as_none: bool = False,
) -> Path:
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_parquet(
        temporary,
        rows,
        field_specs,
        blank_as_none=blank_as_none,
    )
    os.replace(temporary, path)
    return path


def parquet_row_count(path: Path) -> int:
    connection = duckdb.connect(":memory:")
    try:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM read_parquet(?)",
                [str(path)],
            ).fetchone()[0]
        )
    finally:
        connection.close()
