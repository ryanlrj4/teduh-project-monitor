import json

from teduh_monitor.ui.data import apply_shortlist_metadata, dataframe


def test_apply_shortlist_metadata_overlays_local_fields_without_mutating_source() -> None:
    current = [{"source_project_id": "100-1", "display_name": "TEDUH name"}]
    shortlist = [
        {
            "source_project_id": "100-1",
            "display_name": "Local name",
            "parent_group": "Parent Berhad",
            "project_set": "reporting_set",
            "region": "Penang",
        }
    ]

    enriched = apply_shortlist_metadata(current, shortlist)

    assert enriched[0]["display_name"] == "Local name"
    assert enriched[0]["parent_group"] == "Parent Berhad"
    assert enriched[0]["project_set"] == "reporting_set"
    assert current[0]["display_name"] == "TEDUH name"


def test_dataframe_adds_default_region_and_converts_numeric_columns() -> None:
    frame = dataframe(
        [
            {
                "source_project_id": "100-1",
                "sold_units": "42",
                "sales_percentage": "6.9",
                "latitude": "3.1390",
                "longitude": "101.6869",
            }
        ]
    )

    assert frame.loc[0, "region"] == "Kuala Lumpur"
    assert frame.loc[0, "sold_units"] == 42
    assert frame.loc[0, "sales_percentage"] == 6.9
    assert frame.loc[0, "latitude"] == 3.139


def test_dataframe_recovers_legacy_completion_dates_from_component_rows() -> None:
    frame = dataframe(
        [
            {
                "source_project_id": "100-1",
                "construction_rows_json": json.dumps(
                    [
                        {"ccc": "01/02/2026", "vp": "03/02/2026"},
                        {"ccc": "05/02/2026", "vp": "04/02/2026"},
                    ]
                ),
            }
        ]
    )

    assert frame.loc[0, "ccc_date"] == "2026-02-05"
    assert frame.loc[0, "vp_date"] == "2026-02-04"
