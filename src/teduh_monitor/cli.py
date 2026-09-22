from __future__ import annotations

import argparse
import json

from .config import (
    DEFAULT_REGION,
    REGION_CONFIGS,
    Settings,
    project_root,
)
from .discovery import run_discovery
from .monitor import (
    current_metrics_path,
    current_parquet_path,
    history_csv_path,
    snapshot_shortlist,
)
from .schedule import refresh_if_due
from .shortlist import load_shortlist
from .storage import parquet_row_count, read_csv
from .validate import validate_records


def _settings(delay: float = 1.1) -> Settings:
    return Settings(root=project_root(), request_delay_seconds=delay)


def _refresh(args: argparse.Namespace) -> int:
    result = snapshot_shortlist(_settings(args.delay))
    print(
        json.dumps(
            {
                "snapshot_date": result["snapshot_date"],
                "project_count": result["project_count"],
                "alert_count": result["alert_count"],
                "outputs": {name: str(path) for name, path in result["paths"].items()},
            },
            indent=2,
        )
    )
    return 0


def _refresh_if_due(args: argparse.Namespace) -> int:
    result = refresh_if_due(_settings(args.delay))
    print(json.dumps(result, indent=2))
    return 0


def _discover(args: argparse.Namespace) -> int:
    result = run_discovery(_settings(args.delay), region=args.region)
    print(json.dumps({**result, "path": str(result["path"])}, indent=2))
    return 0


def _validate_monitor(_: argparse.Namespace) -> int:
    settings = _settings()
    paths = (
        current_metrics_path(settings),
        current_parquet_path(settings),
        history_csv_path(settings),
    )
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Missing monitor output: {path}")

    current_rows = read_csv(current_metrics_path(settings))
    history_rows = read_csv(history_csv_path(settings))
    active_count = len(load_shortlist(settings, active_only=True))
    if len(current_rows) != active_count:
        raise SystemExit(
            f"Current snapshot has {len(current_rows)} rows but the active shortlist has "
            f"{active_count}"
        )

    history_keys = [
        (row.get("snapshot_date"), row.get("source_project_id")) for row in history_rows
    ]
    if len(history_keys) != len(set(history_keys)):
        raise SystemExit("Shortlist history contains duplicate project/date observations")

    parquet_rows = parquet_row_count(current_parquet_path(settings))
    if parquet_rows != len(current_rows):
        raise SystemExit(
            f"Current Parquet has {parquet_rows} rows but CSV has {len(current_rows)}"
        )

    validation_rows = [
        {field: None if value == "" else value for field, value in row.items()}
        for row in current_rows
    ]
    errors = [
        issue
        for issue in validate_records(validation_rows)
        if issue["severity"] == "error"
    ]
    if errors:
        preview = "; ".join(
            f"{issue['source_project_id']}: {issue['message']}" for issue in errors[:5]
        )
        raise SystemExit(f"Current snapshot contains {len(errors)} validation error(s): {preview}")

    print(
        f"Verified {len(current_rows)} active projects and "
        f"{len(history_rows)} unique dated observations."
    )
    return 0


def _add_delay_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="minimum seconds between public TEDUH requests (default: 1.1)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TEDUH regional project monitor")
    commands = parser.add_subparsers(dest="command", required=True)

    refresh_parser = commands.add_parser(
        "refresh",
        help="refresh active shortlisted projects and update history",
    )
    _add_delay_argument(refresh_parser)
    refresh_parser.set_defaults(func=_refresh)

    scheduled_parser = commands.add_parser(
        "refresh-if-due",
        help="refresh once per Monday-based week when called by a scheduler",
    )
    _add_delay_argument(scheduled_parser)
    scheduled_parser.set_defaults(func=_refresh_if_due)

    discovery_parser = commands.add_parser(
        "discover",
        help="run or reuse a once-per-day regional catalogue discovery",
    )
    discovery_parser.add_argument(
        "--region",
        choices=list(REGION_CONFIGS),
        default=DEFAULT_REGION,
        help=f"TEDUH region to discover (default: {DEFAULT_REGION})",
    )
    _add_delay_argument(discovery_parser)
    discovery_parser.set_defaults(func=_discover)

    monitor_validation = commands.add_parser(
        "validate-monitor",
        help="verify current shortlist and history outputs",
    )
    monitor_validation.set_defaults(func=_validate_monitor)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
