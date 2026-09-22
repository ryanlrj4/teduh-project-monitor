from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


BASE_URL = "https://teduh.kpkt.gov.my"
SEARCH_PAGE_URL = f"{BASE_URL}/semakan-status-kemajuan"
STATE_ID = "14"
DEFAULT_REGION = "Kuala Lumpur"
REGION_CONFIGS = {
    "Kuala Lumpur": {
        "state_id": "14",
        "state_label": "Wp Kuala Lumpur",
        "slug": "kuala_lumpur",
    },
    "Penang": {
        "state_id": "07",
        "state_label": "Pulau Pinang",
        "slug": "penang",
    },
    "Selangor": {
        "state_id": "10",
        "state_label": "Selangor",
        "slug": "selangor",
    },
    "Johor": {
        "state_id": "01",
        "state_label": "Johor",
        "slug": "johor",
    },
    "Malacca": {
        "state_id": "04",
        "state_label": "Melaka",
        "slug": "melaka",
    },
}
TARGET_STATUSES = {
    "0": "Belum Mula",
    "1": "Lancar",
    "2": "Sakit",
    "3": "Lewat",
    "5": "Siap Dengan CCC",
    "7": "Siap Dengan CFO",
}
HIMS_UNIT_DATA_START_DATE = date(2022, 1, 1)
HIMS_UNIT_DATA_START_ISO = HIMS_UNIT_DATA_START_DATE.isoformat()
TRANSFORMATION_VERSION = "1.5.2"
USER_AGENT = "TeduhProjectMonitor/0.2 (local research; sequential public requests)"


@dataclass(frozen=True)
class Settings:
    root: Path
    # TEDUH currently advertises a 60-request-per-minute limit. A small margin
    # above one second keeps this client below that published response limit.
    request_delay_seconds: float = 1.1
    timeout_seconds: float = 60.0
    retries: int = 3
    minimum_expected_projects: int = 100

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.root / "data" / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.root / "data" / "processed"

def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
