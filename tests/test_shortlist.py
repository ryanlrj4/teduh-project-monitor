from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from teduh_monitor.config import Settings
from teduh_monitor.discovery import (
    DISCOVERY_FIELDS,
    discovery_catalog_path,
    discovery_manifest_path,
    run_discovery,
)
from teduh_monitor.shortlist import load_audit_log, load_shortlist, upsert_shortlist_project


def test_shortlist_preserves_manual_name_and_parent_mapping(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": "19760-2",
            "display_name": "Skyline Embassy Ampang",
            "parent_group": "Law Developments",
            "project_set": "comparator_set",
            "priority": "high",  # Legacy input is accepted but intentionally discarded.
            "tracking_notes": "Public monitoring note",
            "active": "Yes",
            "origin": "manual",
        },
    )
    rows = load_shortlist(settings, active_only=True)
    assert rows[0]["display_name"] == "Skyline Embassy Ampang"
    assert rows[0]["parent_group"] == "Law Developments"
    assert rows[0]["project_set"] == "comparator_set"
    assert rows[0]["region"] == "Kuala Lumpur"
    assert "priority" not in rows[0]


def test_shortlist_allows_teduh_name_fallback(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": "14510-2",
            "display_name": "",
            "parent_group": "",
            "project_set": "general",
            "active": "Yes",
        },
    )
    rows = load_shortlist(settings)
    assert rows[0]["display_name"] == ""
    assert rows[0]["source_project_id"] == "14510-2"


def test_shortlist_preserves_penang_region_and_reporting_set(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": "30439-1",
            "region": "Penang",
            "display_name": "The Anton",
            "parent_group": "Tamarins Land",
            "project_set": "reporting_set",
            "active": "Yes",
        },
    )
    rows = load_shortlist(settings)
    assert rows[0]["region"] == "Penang"
    assert rows[0]["project_set"] == "reporting_set"


def test_shortlist_preserves_optional_manual_ranges(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": "14510-2",
            "manual_built_up_min_sqft": "500",
            "manual_built_up_max_sqft": "1,200",
            "manual_psf_min": "800",
            "manual_psf_max": "950",
            "manual_launch_date": "2025-10-01",
        },
    )
    row = load_shortlist(settings)[0]
    assert row["manual_built_up_min_sqft"] == "500"
    assert row["manual_built_up_max_sqft"] == "1200"
    assert row["manual_psf_min"] == "800"
    assert row["manual_psf_max"] == "950"
    assert row["manual_launch_date"] == "2025-10-01"


def test_shortlist_rejects_invalid_optional_launch_date(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    with pytest.raises(ValueError, match="use YYYY-MM-DD"):
        upsert_shortlist_project(
            settings,
            {"source_project_id": "14510-2", "manual_launch_date": "October 2025"},
        )


def test_shortlist_requires_both_ends_of_a_manual_range(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    with pytest.raises(ValueError, match="Both minimum and maximum"):
        upsert_shortlist_project(
            settings,
            {
                "source_project_id": "14510-2",
                "manual_psf_min": "800",
            },
        )


def test_project_addition_is_recorded_in_audit_log(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    upsert_shortlist_project(
        settings,
        {
            "source_project_id": "30744-1",
            "region": "Penang",
            "display_name": "The Crown",
            "parent_group": "Chin Hin",
            "project_set": "general",
        },
        changed_by="RLR",
    )
    audit = load_audit_log(settings)
    assert len(audit) == 1
    assert audit[0]["action"] == "Project added"
    assert audit[0]["changed_by"] == "RLR"
    assert audit[0]["source_project_id"] == "30744-1"
    assert audit[0]["project_name"] == "The Crown"
    assert audit[0]["event_timestamp"]


def test_project_edits_are_recorded_field_by_field(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    original = {
        "source_project_id": "30744-1",
        "region": "Penang",
        "display_name": "The Crown",
        "parent_group": "Chin Hin",
        "project_set": "general",
        "active": "Yes",
    }
    upsert_shortlist_project(settings, original, changed_by="RLR")
    upsert_shortlist_project(
        settings,
        {
            **original,
            "parent_group": "Chin Hin Group",
            "project_set": "reporting_set",
        },
        changed_by="ABC",
    )
    audit = load_audit_log(settings)
    edits = [row for row in audit if row["action"] == "Project edited"]
    assert len(edits) == 2
    assert {row["field"] for row in edits} == {"Parent group", "Project set"}
    parent_change = next(row for row in edits if row["field"] == "Parent group")
    assert parent_change["previous_value"] == "Chin Hin"
    assert parent_change["new_value"] == "Chin Hin Group"
    assert parent_change["changed_by"] == "ABC"


def test_saving_without_changes_does_not_add_audit_noise(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    row = {
        "source_project_id": "30744-1",
        "region": "Penang",
        "display_name": "The Crown",
        "project_set": "general",
    }
    upsert_shortlist_project(settings, row, changed_by="RLR")
    upsert_shortlist_project(settings, row, changed_by="RLR")
    audit = load_audit_log(settings)
    assert [event["action"] for event in audit] == ["Project added"]


def test_same_day_discovery_reuses_catalog_without_live_request(tmp_path) -> None:
    settings = Settings(root=tmp_path)
    today = date.today().isoformat()
    catalog = discovery_catalog_path(settings)
    catalog.parent.mkdir(parents=True)
    with catalog.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DISCOVERY_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "discovery_date": today,
                "source_project_id": "19760-2",
                "registry_name": "Residensi Skyline Duta Ampang",
            }
        )
    manifest = discovery_manifest_path(settings)
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "discovery_date": today,
                "project_count": 1,
                "status_counts": {"Siap Dengan CCC": 1},
            }
        ),
        encoding="utf-8",
    )
    result = run_discovery(settings, progress=lambda _: None)
    assert result["live_request_performed"] is False
    assert result["project_count"] == 1
