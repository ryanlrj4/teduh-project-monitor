from __future__ import annotations

import csv
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULT_REGION, REGION_CONFIGS, Settings
from .sources import TeduhClient, fetch_project_catalog
from .shortlist import load_shortlist


Progress = Callable[[str], None]
DISCOVERY_FIELDS = [
    "discovery_date",
    "region",
    "source_project_id",
    "registry_name",
    "developer_id",
    "developer_name",
    "project_status",
    "state_id",
    "district_id",
    "city_id",
    "latitude",
    "longitude",
    "currently_tracked",
]


def discovery_catalog_path(settings: Settings, region: str = DEFAULT_REGION) -> Path:
    slug = str(REGION_CONFIGS[region]["slug"])
    return settings.processed_dir / f"{slug}_discovery_catalog.csv"


def discovery_manifest_path(settings: Settings, region: str = DEFAULT_REGION) -> Path:
    slug = str(REGION_CONFIGS[region]["slug"])
    return settings.interim_dir / f"discovery_{slug}_last_success.json"


def load_discovery_catalog(
    settings: Settings, region: str = DEFAULT_REGION
) -> list[dict[str, str]]:
    path = discovery_catalog_path(settings, region)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DISCOVERY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def run_discovery(
    settings: Settings,
    *,
    region: str = DEFAULT_REGION,
    progress: Progress = print,
) -> dict[str, Any]:
    """Run at most one live catalogue discovery per region and local calendar day."""
    if region not in REGION_CONFIGS:
        raise ValueError(f"Unsupported discovery region: {region}")
    region_config = REGION_CONFIGS[region]
    today = date.today().isoformat()
    manifest_path = discovery_manifest_path(settings, region)
    catalog_path = discovery_catalog_path(settings, region)
    if manifest_path.exists() and catalog_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("discovery_date") == today:
            rows = load_discovery_catalog(settings, region)
            progress(f"{region} Discovery already ran today; reused the cached catalogue.")
            return {
                "discovery_date": today,
                "region": region,
                "live_request_performed": False,
                "project_count": len(rows),
                "status_counts": manifest.get("status_counts") or {},
                "path": catalog_path,
            }

    tracked = {row["source_project_id"] for row in load_shortlist(settings, active_only=True)}
    progress(f"Starting the daily-capped {region} TEDUH discovery catalogue scan.")
    with TeduhClient(settings, snapshot_date=today, force=False) as client:
        projects, counts = fetch_project_catalog(
            client, state_id=str(region_config["state_id"])
        )
    rows: list[dict[str, Any]] = []
    for project in projects:
        developer = project.get("pemaju") or {}
        status = project.get("status_project") or {}
        project_code = str(project.get("id") or "").strip()
        rows.append(
            {
                "discovery_date": today,
                "region": region,
                "source_project_id": project_code,
                "registry_name": project.get("nama") or "",
                "developer_id": project.get("kod_pemaju") or developer.get("kod_pemaju") or "",
                "developer_name": developer.get("nama") or "",
                "project_status": status.get("keterangan") or "",
                "state_id": project.get("kod_negeri_id") or "",
                "district_id": project.get("kod_daerah_id") or "",
                "city_id": project.get("kod_bandar_id") or "",
                "latitude": project.get("latitud") or "",
                "longitude": project.get("longitud") or "",
                "currently_tracked": "Yes" if project_code in tracked else "No",
            }
        )
    rows.sort(key=lambda row: (str(row["registry_name"]).casefold(), row["source_project_id"]))
    _atomic_csv(catalog_path, rows)
    _atomic_json(
        manifest_path,
        {
            "discovery_date": today,
            "region": region,
            "project_count": len(rows),
            "status_counts": counts,
            "path": str(catalog_path),
        },
    )
    progress(f"Discovery completed with {len(rows)} {region} catalogue projects.")
    return {
        "discovery_date": today,
        "region": region,
        "live_request_performed": True,
        "project_count": len(rows),
        "status_counts": counts,
        "path": catalog_path,
    }
