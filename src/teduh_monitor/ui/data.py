from __future__ import annotations

import pandas as pd

from ..config import DEFAULT_REGION
from ..migrations import backfill_legacy_completion_dates, backfill_v15_derived_metrics
from ..storage import read_csv


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
    frame = backfill_legacy_completion_dates(frame)
    frame = backfill_v15_derived_metrics(frame)
    for column in (
        "reported_total_units",
        "sold_units",
        "unsold_units",
        "booked_or_reserved_units",
        "unknown_sales_status_units",
        "comparable_total_units",
        "sales_percentage",
        "value_sold_percentage",
        "sales_construction_gap",
        "construction_percentage",
        "manual_built_up_min_sqft",
        "manual_built_up_max_sqft",
        "manual_psf_min",
        "manual_psf_max",
        "teduh_spa_price_min",
        "teduh_spa_price_max",
        "potential_listed_gdv",
        "average_listed_price_per_unit",
        "median_listed_price_per_unit",
        "listed_price_p25",
        "listed_price_p75",
        "sold_listed_value",
        "recorded_spa_sales_value",
        "average_recorded_spa_price_per_unit",
        "median_recorded_spa_price_per_unit",
        "estimated_sold_value",
        "remaining_listed_value",
        "recorded_price_realisation_percentage",
        "median_recorded_discount_percentage",
        "bumi_total_units",
        "bumi_sold_units",
        "bumi_unsold_units",
        "bumi_sales_percentage",
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
