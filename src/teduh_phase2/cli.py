from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import duckdb

from .config import DEFAULT_REGION, HIMS_UNIT_DATA_START_ISO, REGION_CONFIGS, Settings, project_root
from .discovery import run_discovery
from .monitor import (
    current_metrics_path,
    current_parquet_path,
    history_csv_path,
    snapshot_shortlist,
    validation_path,
)
from .pipeline import run_pipeline
from .schedule import refresh_if_due
from .shortlist import load_shortlist


def _run(args: argparse.Namespace) -> int:
    settings = Settings(
        root=project_root(),
        request_delay_seconds=args.delay,
    )
    result = run_pipeline(settings, force=args.force)
    summary = {
        "snapshot_date": result["snapshot_date"],
        "catalog_project_count": result["catalog_project_count"],
        "project_count": result["project_count"],
        "excluded_legacy_projects": result["excluded_legacy_projects"],
        "status_counts": result["status_counts"],
        "validation_project_ids": [row["source_project_id"] for row in result["validation"]],
        "outputs": {name: str(path) for name, path in result["paths"].items()},
    }
    print(json.dumps(summary, indent=2))
    return 0


def _validate_outputs(_: argparse.Namespace) -> int:
    root = project_root()
    csv_path = root / "data" / "processed" / "kl_project_metrics_hims_eligible.csv"
    parquet_path = root / "data" / "processed" / "kl_project_metrics_hims_eligible.parquet"
    validation_path = root / "data" / "processed" / "kl_validation_sample_hims_eligible.csv"
    for path in (csv_path, parquet_path, validation_path):
        if not path.exists():
            raise SystemExit(f"Missing output: {path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    with validation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        validation_rows = list(csv.DictReader(handle))
    connection = duckdb.connect(":memory:")
    try:
        parquet_rows = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(parquet_path)]
        ).fetchone()[0]
    finally:
        connection.close()
    if len(csv_rows) != parquet_rows:
        raise SystemExit(f"CSV has {len(csv_rows)} rows but Parquet has {parquet_rows}")
    if len(validation_rows) != 5:
        raise SystemExit(f"Validation CSV has {len(validation_rows)} rows; expected exactly 5")
    legacy_rows = [
        row
        for row in csv_rows
        if not row.get("hims_project_reference_date")
        or row["hims_project_reference_date"] < HIMS_UNIT_DATA_START_ISO
    ]
    if legacy_rows:
        raise SystemExit(
            f"Metrics CSV contains {len(legacy_rows)} rows before the HIMS cutoff "
            f"{HIMS_UNIT_DATA_START_ISO}"
        )
    invalid_ccc = [row for row in csv_rows if row.get("ccc_obtained") not in {"Yes", "No"}]
    if invalid_ccc:
        raise SystemExit(f"Metrics CSV contains {len(invalid_ccc)} invalid CCC flags")
    forbidden_columns = {"ccc_or_cfo_date", "booked_or_reserved_units", "unknown_sales_status_units"}
    present_forbidden = forbidden_columns.intersection(csv_rows[0] if csv_rows else {})
    if present_forbidden:
        raise SystemExit(f"Metrics CSV still contains removed columns: {sorted(present_forbidden)}")
    print(f"Verified {len(csv_rows)} metric rows and exactly 5 validation rows.")
    return 0


def _snapshot_shortlist(args: argparse.Namespace) -> int:
    settings = Settings(root=project_root(), request_delay_seconds=args.delay)
    result = snapshot_shortlist(settings)
    print(
        json.dumps(
            {
                "snapshot_date": result["snapshot_date"],
                "project_count": result["project_count"],
                "alert_count": result["alert_count"],
                "validation_project_ids": [
                    row["source_project_id"] for row in result["validation"]
                ],
                "outputs": {name: str(path) for name, path in result["paths"].items()},
            },
            indent=2,
        )
    )
    return 0


def _discover(args: argparse.Namespace) -> int:
    settings = Settings(root=project_root(), request_delay_seconds=args.delay)
    result = run_discovery(settings, region=args.region)
    print(json.dumps({**result, "path": str(result["path"])}, indent=2))
    return 0


def _refresh_if_due(args: argparse.Namespace) -> int:
    settings = Settings(root=project_root(), request_delay_seconds=args.delay)
    result = refresh_if_due(settings)
    print(json.dumps(result, indent=2))
    return 0


def _validate_phase3(_: argparse.Namespace) -> int:
    settings = Settings(root=project_root())
    paths = (
        current_metrics_path(settings),
        current_parquet_path(settings),
        history_csv_path(settings),
        validation_path(settings),
    )
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Missing Phase 3 output: {path}")
    current_rows = list(csv.DictReader(current_metrics_path(settings).open("r", encoding="utf-8-sig", newline="")))
    history_rows = list(csv.DictReader(history_csv_path(settings).open("r", encoding="utf-8-sig", newline="")))
    validation_rows = list(csv.DictReader(validation_path(settings).open("r", encoding="utf-8-sig", newline="")))
    active_count = len(load_shortlist(settings, active_only=True))
    if len(current_rows) != active_count:
        raise SystemExit(f"Current snapshot has {len(current_rows)} rows but active shortlist has {active_count}")
    if len(validation_rows) != 5:
        raise SystemExit(f"Phase 3 validation contains {len(validation_rows)} rows; expected exactly 5")
    history_keys = [(row.get("snapshot_date"), row.get("source_project_id")) for row in history_rows]
    if len(history_keys) != len(set(history_keys)):
        raise SystemExit("Shortlist history contains duplicate project/date observations")
    connection = duckdb.connect(":memory:")
    try:
        parquet_rows = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(current_parquet_path(settings))]
        ).fetchone()[0]
    finally:
        connection.close()
    if parquet_rows != len(current_rows):
        raise SystemExit(f"Current Parquet has {parquet_rows} rows but CSV has {len(current_rows)}")
    if not any(row.get("ccc_obtained") == "Yes" for row in current_rows):
        raise SystemExit("Phase 3 snapshot has no completed CCC/CFO project")
    print(
        f"Verified {len(current_rows)} shortlist projects, {len(history_rows)} unique dated observations, "
        "and exactly 5 Phase 3 validation rows."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TEDUH regional project monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="retrieve TEDUH data and generate outputs")
    run_parser.add_argument("--force", action="store_true", help="ignore today's valid raw cache")
    run_parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="minimum seconds between public TEDUH requests (default: 1.1)",
    )
    run_parser.set_defaults(func=_run)
    validate_parser = subparsers.add_parser("validate", help="verify generated output row counts")
    validate_parser.set_defaults(func=_validate_outputs)
    snapshot_parser = subparsers.add_parser(
        "snapshot-shortlist", help="refresh only active shortlist projects and update history"
    )
    snapshot_parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="minimum seconds between public TEDUH requests (default: 1.1)",
    )
    snapshot_parser.set_defaults(func=_snapshot_shortlist)
    scheduled_parser = subparsers.add_parser(
        "refresh-if-due",
        help="refresh once in each Monday-based week when called by a scheduler",
    )
    scheduled_parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="minimum seconds between public TEDUH requests (default: 1.1)",
    )
    scheduled_parser.set_defaults(func=_refresh_if_due)
    discovery_parser = subparsers.add_parser(
        "discover", help="run or reuse a once-per-day regional catalogue discovery"
    )
    discovery_parser.add_argument(
        "--region",
        choices=list(REGION_CONFIGS),
        default=DEFAULT_REGION,
        help=f"TEDUH region to discover (default: {DEFAULT_REGION})",
    )
    discovery_parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="minimum seconds between public TEDUH requests (default: 1.1)",
    )
    discovery_parser.set_defaults(func=_discover)
    phase3_validate = subparsers.add_parser(
        "validate-phase3", help="verify shortlist, history, CCC/CFO, and five validation rows"
    )
    phase3_validate.set_defaults(func=_validate_phase3)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
