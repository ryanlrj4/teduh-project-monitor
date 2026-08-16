from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import BASE_URL, STATE_ID, TARGET_STATUSES, USER_AGENT, Settings


class SourceAnomaly(RuntimeError):
    """Raised when a response is unsafe to treat as source data."""


@dataclass(frozen=True)
class SourceResult:
    payload: Any
    retrieved_at: str
    url: str
    cache_path: Path
    from_cache: bool


class TeduhClient:
    """Small sequential client for the public GET requests used by TEDUH's page."""

    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_date: str,
        force: bool = False,
    ) -> None:
        self.settings = settings
        self.snapshot_date = snapshot_date
        self.force = force
        self._last_request_at = 0.0
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=settings.timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TeduhClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.settings.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _cache_paths(self, relative: Path) -> tuple[Path, Path]:
        body = self.settings.raw_dir / "teduh" / self.snapshot_date / relative
        meta = body.with_suffix(body.suffix + ".metadata.json")
        return body, meta

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    @staticmethod
    def _validate_payload(payload: Any, expected_keys: tuple[str, ...], url: str) -> None:
        if not isinstance(payload, (dict, list)):
            raise SourceAnomaly(f"Expected JSON object or list from {url}")
        if expected_keys:
            if not isinstance(payload, dict):
                raise SourceAnomaly(f"Expected JSON object with keys {expected_keys} from {url}")
            missing = [key for key in expected_keys if key not in payload]
            if missing:
                raise SourceAnomaly(f"Schema changed at {url}; missing keys: {missing}")

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        cache_relative: Path,
        expected_keys: tuple[str, ...] = (),
    ) -> SourceResult:
        body_path, meta_path = self._cache_paths(cache_relative)
        if body_path.exists() and meta_path.exists() and not self.force:
            raw = body_path.read_bytes()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            payload = json.loads(raw.decode("utf-8"))
            self._validate_payload(payload, expected_keys, meta["url"])
            return SourceResult(
                payload=payload,
                retrieved_at=meta["retrieved_at"],
                url=meta["url"],
                cache_path=body_path,
                from_cache=True,
            )

        last_error: Exception | None = None
        for attempt in range(self.settings.retries):
            try:
                self._wait()
                response = self._client.get(path, params=params)
                self._last_request_at = time.monotonic()
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    try:
                        wait_seconds = max(float(retry_after or 0), 15.0)
                    except ValueError:
                        wait_seconds = 15.0
                    if attempt + 1 < self.settings.retries:
                        time.sleep(wait_seconds)
                        continue
                    raise SourceAnomaly(
                        f"TEDUH rate limit persisted for {response.request.url}"
                    )
                if response.status_code >= 500:
                    raise SourceAnomaly(
                        f"TEDUH returned HTTP {response.status_code} for {response.request.url}"
                    )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                prefix = response.content.lstrip()[:80].lower()
                if "json" not in content_type or prefix.startswith(b"<html") or prefix.startswith(b"<!doctype"):
                    raise SourceAnomaly(
                        f"Expected JSON but received {content_type or 'unknown content'} from {response.request.url}"
                    )
                payload = response.json()
                url = str(response.request.url)
                self._validate_payload(payload, expected_keys, url)
                retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
                metadata = {
                    "url": url,
                    "retrieved_at": retrieved_at,
                    "http_status": response.status_code,
                    "content_type": content_type,
                }
                self._atomic_write(body_path, response.content)
                self._atomic_write(
                    meta_path,
                    json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
                )
                return SourceResult(payload, retrieved_at, url, body_path, False)
            except (httpx.HTTPError, ValueError, SourceAnomaly) as exc:
                last_error = exc
                if attempt + 1 < self.settings.retries:
                    time.sleep(2**attempt)
        raise SourceAnomaly(str(last_error) if last_error else f"Failed to retrieve {path}")

    def states(self) -> SourceResult:
        return self.get_json(
            "/api/negeri",
            params=None,
            cache_relative=Path("lookups/states.json"),
        )

    def districts(self) -> SourceResult:
        return self.get_json(
            "/api/daerah-by-negeri",
            params={"negeri_id": STATE_ID},
            cache_relative=Path("lookups/kl_districts.json"),
        )

    def cities(self, district_id: str) -> SourceResult:
        return self.get_json(
            "/api/bandar-by-daerah",
            params={"daerah_id": district_id},
            cache_relative=Path(f"lookups/cities_{district_id}.json"),
        )

    def search_projects(self, status_id: str, page: int, *, state_id: str = STATE_ID) -> SourceResult:
        return self.get_json(
            "/api/projek-swasta",
            params={
                "page": page,
                "search_type": "projek",
                "state": state_id,
                "statusProjek": status_id,
            },
            cache_relative=Path(f"search/state_{state_id}/status_{status_id}/page_{page}.json"),
            expected_keys=("projects", "statuses", "totalVisibleProjects"),
        )

    def project_detail(self, project_code: str) -> SourceResult:
        return self.get_json(
            f"/api/projek-swasta/{project_code}",
            params=None,
            cache_relative=Path(f"projects/{project_code}.json"),
            expected_keys=("pemaju", "projek", "unitSummary", "pjb", "status"),
        )

    def project_units(self, project_code: str) -> SourceResult:
        return self.get_json(
            f"/api/unit-projek-swasta/{project_code}",
            params=None,
            cache_relative=Path(f"units/{project_code}.json"),
            expected_keys=("unitGroups",),
        )


def fetch_project_catalog(
    client: TeduhClient, *, state_id: str = STATE_ID
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    projects_by_id: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for status_id, expected_label in TARGET_STATUSES.items():
        first = client.search_projects(status_id, 1, state_id=state_id).payload
        project_page = first["projects"]
        total = int(project_page.get("total", 0))
        last_page = int(project_page.get("last_page", 0))
        per_page = int(project_page.get("per_page", 0))
        if total <= 0 or last_page <= 0 or per_page <= 0:
            raise SourceAnomaly(f"Empty or malformed project search for status {expected_label}")
        counts[expected_label] = total
        pages = [first]
        for page in range(2, last_page + 1):
            pages.append(client.search_projects(status_id, page, state_id=state_id).payload)
        status_rows = []
        for payload in pages:
            status_rows.extend(payload["projects"].get("data") or [])
        if len(status_rows) != total:
            raise SourceAnomaly(
                f"Pagination mismatch for {expected_label}: expected {total}, received {len(status_rows)}"
            )
        for project in status_rows:
            project_id = str(project.get("id") or "").strip()
            if not project_id:
                raise SourceAnomaly(f"Project without an id in {expected_label} results")
            if project_id in projects_by_id:
                raise SourceAnomaly(f"Duplicate project id across status results: {project_id}")
            projects_by_id[project_id] = project
    if len(projects_by_id) < client.settings.minimum_expected_projects:
        raise SourceAnomaly(
            f"Only {len(projects_by_id)} projects found; safety minimum is "
            f"{client.settings.minimum_expected_projects}"
        )
    return list(projects_by_id.values()), counts


def encoded_url(path: str, params: dict[str, Any]) -> str:
    return f"{BASE_URL}{path}?{urlencode(params)}"
