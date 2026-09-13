from __future__ import annotations

import json

import pandas as pd

from .metrics import component_completion_dates


def backfill_legacy_completion_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive completion dates for snapshots created before those fields existed."""
    if frame.empty:
        return frame

    migrated = frame.copy()
    for field in ("ccc_date", "vp_date"):
        if field not in migrated.columns:
            migrated[field] = None
    if "construction_rows_json" not in migrated.columns:
        return migrated

    for index, raw_rows in migrated["construction_rows_json"].items():
        if (
            migrated.at[index, "ccc_date"] not in (None, "")
            and migrated.at[index, "vp_date"] not in (None, "")
        ):
            continue
        try:
            rows = json.loads(raw_rows or "[]")
            ccc_date, vp_date = component_completion_dates(rows)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if migrated.at[index, "ccc_date"] in (None, ""):
            migrated.at[index, "ccc_date"] = ccc_date
        if migrated.at[index, "vp_date"] in (None, ""):
            migrated.at[index, "vp_date"] = vp_date
    return migrated


def backfill_v15_derived_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Populate v1.5 ratios that can be derived from an existing observation."""
    if frame.empty:
        return frame
    migrated = frame.copy()
    numeric_sources = (
        "estimated_sold_value",
        "potential_listed_gdv",
        "sales_percentage",
        "construction_percentage",
    )
    for field in numeric_sources:
        if field not in migrated.columns:
            migrated[field] = pd.NA
        migrated[field] = pd.to_numeric(migrated[field], errors="coerce")

    if "value_sold_percentage" not in migrated.columns:
        migrated["value_sold_percentage"] = pd.NA
    denominator = migrated["potential_listed_gdv"].where(
        migrated["potential_listed_gdv"] > 0
    )
    derived_value_sold = migrated["estimated_sold_value"] / denominator * 100
    migrated["value_sold_percentage"] = pd.to_numeric(
        migrated["value_sold_percentage"], errors="coerce"
    ).fillna(derived_value_sold)

    if "sales_construction_gap" not in migrated.columns:
        migrated["sales_construction_gap"] = pd.NA
    derived_gap = migrated["sales_percentage"] - migrated["construction_percentage"]
    migrated["sales_construction_gap"] = pd.to_numeric(
        migrated["sales_construction_gap"], errors="coerce"
    ).fillna(derived_gap)
    for field in (
        "average_listed_price_per_unit",
        "median_listed_price_per_unit",
        "listed_price_p25",
        "listed_price_p75",
        "sold_listed_value",
        "average_recorded_spa_price_per_unit",
        "median_recorded_spa_price_per_unit",
        "recorded_price_realisation_percentage",
        "median_recorded_discount_percentage",
        "bumi_total_units",
        "bumi_sold_units",
        "bumi_unsold_units",
        "bumi_sales_percentage",
    ):
        if field not in migrated.columns:
            migrated[field] = pd.NA

    priced_count = pd.to_numeric(
        migrated.get("priced_unit_records_count", pd.Series(index=migrated.index, dtype=float)),
        errors="coerce",
    ).where(lambda values: values > 0)
    average_listed = migrated["potential_listed_gdv"] / priced_count
    migrated["average_listed_price_per_unit"] = pd.to_numeric(
        migrated["average_listed_price_per_unit"], errors="coerce"
    ).fillna(average_listed)
    if "remaining_inventory_json" not in migrated.columns:
        migrated["remaining_inventory_json"] = ""
    return migrated
