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
