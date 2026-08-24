from pathlib import Path

import pytest

from teduh_phase2.collection import IneligibleProject, collect_project
from teduh_phase2.sources import SourceAnomaly, SourceResult


def source_result(payload, *, retrieved_at: str, from_cache: bool) -> SourceResult:
    return SourceResult(
        payload=payload,
        retrieved_at=retrieved_at,
        url="https://teduh.example/api",
        cache_path=Path("cache.json"),
        from_cache=from_cache,
    )


def detail_payload(*, state: str = "WP Kuala Lumpur", first_spa: str = "2026-01-01"):
    return {
        "nama": "Synthetic Project",
        "projek": {
            "kod_projek": "999-1",
            "nama": "Synthetic Project",
            "negeri": state,
            "permitMula": "2025-01-01",
        },
        "pemaju": {
            "kod_pemaju": "999",
            "nama": "Synthetic Developer",
            "latest_lesen": {},
        },
        "unitSummary": {"unit": 1},
        "pjb": {"tarikhPjbPertama": first_spa},
        "status": {"keseluruhan": "Lancar", "rows": []},
    }


class FakeClient:
    def __init__(
        self,
        detail,
        *,
        units=None,
        unit_error: SourceAnomaly | None = None,
    ) -> None:
        self.detail = detail
        self.units = units or {"unitGroups": []}
        self.unit_error = unit_error
        self.unit_calls = 0

    def project_detail(self, project_code: str) -> SourceResult:
        return source_result(
            self.detail,
            retrieved_at="2026-08-24T10:00:00+08:00",
            from_cache=True,
        )

    def project_units(self, project_code: str) -> SourceResult:
        self.unit_calls += 1
        if self.unit_error is not None:
            raise self.unit_error
        return source_result(
            self.units,
            retrieved_at="2026-08-24T10:01:00+08:00",
            from_cache=False,
        )


def test_collect_project_builds_shortlist_search_envelope_and_cache_metadata() -> None:
    client = FakeClient(
        detail_payload(),
        units={
            "unitGroups": [
                {
                    "pembangunan_id": 1,
                    "jenis": "Apartment",
                    "units": [
                        {
                            "no": "A-1",
                            "status": "sold",
                            "statusJualan": "Telah Dijual",
                            "hargaJualan": "100000",
                            "hargaSPJB": "90000",
                        }
                    ],
                }
            ]
        },
    )

    collected = collect_project(
        client,
        project_code="999-1",
        snapshot_date="2026-08-24",
        source_dataset_as_of="2026-08-23",
        expected_state="Wp Kuala Lumpur",
        expected_region="Kuala Lumpur",
    )

    assert collected.record["project_name"] == "Synthetic Project"
    assert collected.record["developer_id"] == "999"
    assert collected.record["project_status"] == "Lancar"
    assert collected.record["sold_units"] == 1
    assert collected.record["retrieved_at"] == "2026-08-24T10:01:00+08:00"
    assert collected.detail_from_cache is True
    assert collected.units_from_cache is False
    assert collected.unit_error is None


def test_collect_project_rejects_region_mismatch_before_units_request() -> None:
    client = FakeClient(detail_payload(state="Pulau Pinang"))

    with pytest.raises(SourceAnomaly, match="not the selected Kuala Lumpur region"):
        collect_project(
            client,
            project_code="999-1",
            snapshot_date="2026-08-24",
            source_dataset_as_of="2026-08-23",
            expected_state="Wp Kuala Lumpur",
            expected_region="Kuala Lumpur",
        )

    assert client.unit_calls == 0


def test_collect_project_rejects_legacy_project_before_units_request() -> None:
    client = FakeClient(detail_payload(first_spa="2022-01-01"))

    with pytest.raises(IneligibleProject, match="predates comparable HIMS coverage"):
        collect_project(
            client,
            project_code="999-1",
            snapshot_date="2026-08-24",
            source_dataset_as_of="2026-08-23",
        )

    assert client.unit_calls == 0


def test_missing_units_policy_remains_strict_or_tolerant_by_workflow() -> None:
    error = SourceAnomaly("units unavailable")
    strict_client = FakeClient(detail_payload(), unit_error=error)
    with pytest.raises(SourceAnomaly, match="units unavailable"):
        collect_project(
            strict_client,
            project_code="999-1",
            snapshot_date="2026-08-24",
            source_dataset_as_of="2026-08-23",
        )

    tolerant_client = FakeClient(detail_payload(), unit_error=error)
    collected = collect_project(
        tolerant_client,
        project_code="999-1",
        snapshot_date="2026-08-24",
        source_dataset_as_of="2026-08-23",
        allow_missing_units=True,
    )

    assert collected.unit_error is error
    assert collected.units_from_cache is None
    assert collected.record["unit_records_count"] == 0
    assert collected.record["retrieved_at"] == "2026-08-24T10:00:00+08:00"
