from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from ..config import DEFAULT_REGION
from ..metrics import component_completion_dates


SHORTLIST_OVERLAY_FIELDS = (
    "region",
    "display_name",
    "parent_group",
    "project_set",
    "manual_launch_date",
    "manual_built_up_min_sqft",
    "manual_built_up_max_sqft",
    "manual_psf_min",
    "manual_psf_max",
    "tracking_notes",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def apply_shortlist_metadata(
    current_rows: list[dict[str, str]],
    shortlist_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    shortlist_by_project = {
        row["source_project_id"]: row
        for row in shortlist_rows
    }
    enriched: list[dict[str, str]] = []
    for current in current_rows:
        row = dict(current)
        tracked = shortlist_by_project.get(str(row.get("source_project_id") or ""))
        if tracked:
            for field in SHORTLIST_OVERLAY_FIELDS:
                row[field] = tracked.get(field, "")
        enriched.append(row)
    return enriched


def dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if not frame.empty and "region" not in frame.columns:
        frame["region"] = DEFAULT_REGION
    if not frame.empty:
        for field in ("ccc_date", "vp_date"):
            if field not in frame.columns:
                frame[field] = None
        if "construction_rows_json" in frame.columns:
            for index, raw_rows in frame["construction_rows_json"].items():
                if (
                    frame.at[index, "ccc_date"] not in (None, "")
                    and frame.at[index, "vp_date"] not in (None, "")
                ):
                    continue
                try:
                    ccc_date, vp_date = component_completion_dates(json.loads(raw_rows or "[]"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if frame.at[index, "ccc_date"] in (None, ""):
                    frame.at[index, "ccc_date"] = ccc_date
                if frame.at[index, "vp_date"] in (None, ""):
                    frame.at[index, "vp_date"] = vp_date
    for column in (
        "reported_total_units",
        "sold_units",
        "comparable_total_units",
        "sales_percentage",
        "construction_percentage",
        "manual_built_up_min_sqft",
        "manual_built_up_max_sqft",
        "manual_psf_min",
        "manual_psf_max",
        "teduh_spa_price_min",
        "teduh_spa_price_max",
        "potential_listed_gdv",
        "recorded_spa_sales_value",
        "estimated_sold_value",
        "remaining_listed_value",
        "unit_coverage_percentage",
        "listed_price_coverage_percentage",
        "spa_price_coverage_percentage",
        "developer_project_count",
        "latitude",
        "longitude",
        "component_sales_count",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame
