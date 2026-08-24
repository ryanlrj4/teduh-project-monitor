import json

import pandas as pd

from teduh_monitor.migrations import backfill_legacy_completion_dates


def test_legacy_completion_backfill_preserves_existing_values() -> None:
    frame = pd.DataFrame(
        [
            {
                "ccc_date": "2026-01-01",
                "vp_date": "",
                "construction_rows_json": json.dumps(
                    [{"ccc": "05/02/2026", "vp": "04/02/2026"}]
                ),
            }
        ]
    )

    migrated = backfill_legacy_completion_dates(frame)

    assert migrated.loc[0, "ccc_date"] == "2026-01-01"
    assert migrated.loc[0, "vp_date"] == "2026-02-04"
    assert frame.loc[0, "vp_date"] == ""


def test_legacy_completion_backfill_ignores_malformed_component_data() -> None:
    frame = pd.DataFrame([{"construction_rows_json": "not-json"}])

    migrated = backfill_legacy_completion_dates(frame)

    assert migrated.loc[0, "ccc_date"] is None
    assert migrated.loc[0, "vp_date"] is None
