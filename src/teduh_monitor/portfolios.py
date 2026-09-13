from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings
from .shortlist import PROJECT_SETS
from .storage import atomic_write_csv, read_csv


PORTFOLIO_FIELDS = ("portfolio_id", "portfolio_name", "description", "active")
MEMBERSHIP_FIELDS = ("portfolio_id", "source_project_id", "project_set")
MASTER_PORTFOLIO_ID = "admin"


def portfolios_path(settings: Settings) -> Path:
    return settings.root / "config" / "portfolios.csv"


def portfolio_memberships_path(settings: Settings) -> Path:
    return settings.root / "config" / "portfolio_projects.csv"


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")
    if not slug:
        raise ValueError("Portfolio name is required")
    return slug


def load_portfolios(settings: Settings) -> list[dict[str, str]]:
    rows = read_csv(portfolios_path(settings))
    if not rows:
        rows = [
            {
                "portfolio_id": MASTER_PORTFOLIO_ID,
                "portfolio_name": "Admin / Master Portfolio",
                "description": "All tracked projects using the master project classifications.",
                "active": "Yes",
            }
        ]
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        portfolio_id = _slug(row.get("portfolio_id") or row.get("portfolio_name"))
        if portfolio_id in seen:
            raise ValueError(f"Duplicate portfolio id: {portfolio_id}")
        seen.add(portfolio_id)
        result.append(
            {
                "portfolio_id": portfolio_id,
                "portfolio_name": str(row.get("portfolio_name") or portfolio_id).strip(),
                "description": str(row.get("description") or "").strip(),
                "active": "No"
                if str(row.get("active") or "Yes").strip().casefold() in {"no", "false", "0"}
                else "Yes",
            }
        )
    return result


def load_portfolio_memberships(settings: Settings) -> list[dict[str, str]]:
    rows = read_csv(portfolio_memberships_path(settings))
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        portfolio_id = _slug(row.get("portfolio_id"))
        project_code = str(row.get("source_project_id") or "").strip()
        project_set = str(row.get("project_set") or "general").strip().casefold()
        if not project_code:
            continue
        if project_set not in PROJECT_SETS:
            raise ValueError(f"Invalid project set for {portfolio_id}/{project_code}: {project_set}")
        key = (portfolio_id, project_code)
        if key in seen:
            raise ValueError(f"Duplicate portfolio membership: {portfolio_id}/{project_code}")
        seen.add(key)
        result.append(
            {
                "portfolio_id": portfolio_id,
                "source_project_id": project_code,
                "project_set": project_set,
            }
        )
    return result


def portfolio_current(
    current: pd.DataFrame,
    shortlist_rows: list[dict[str, str]],
    memberships: list[dict[str, str]],
    portfolio_id: str,
) -> pd.DataFrame:
    """Return one portfolio view without duplicating underlying TEDUH observations."""
    if current.empty:
        return current.copy()
    if portfolio_id == MASTER_PORTFOLIO_ID:
        return current.copy()

    profile_memberships = {
        row["source_project_id"]: row["project_set"]
        for row in memberships
        if row["portfolio_id"] == portfolio_id
    }
    view = current[
        current["source_project_id"].astype(str).isin(profile_memberships)
    ].copy()
    if not view.empty:
        view["project_set"] = view["source_project_id"].astype(str).map(profile_memberships)
    return view


def portfolio_shortlist(
    shortlist_rows: list[dict[str, str]],
    memberships: list[dict[str, str]],
    portfolio_id: str,
) -> list[dict[str, str]]:
    if portfolio_id == MASTER_PORTFOLIO_ID:
        return [dict(row) for row in shortlist_rows]
    profile_memberships = {
        row["source_project_id"]: row["project_set"]
        for row in memberships
        if row["portfolio_id"] == portfolio_id
    }
    rows: list[dict[str, str]] = []
    for shortlist_row in shortlist_rows:
        code = shortlist_row["source_project_id"]
        if code in profile_memberships:
            row = dict(shortlist_row)
            row["project_set"] = profile_memberships[code]
            rows.append(row)
    return rows


def save_portfolio(
    settings: Settings,
    *,
    portfolio_id: str | None,
    name: str,
    description: str,
    project_sets: dict[str, str],
) -> str:
    new_id = _slug(portfolio_id or name)
    if new_id == MASTER_PORTFOLIO_ID:
        raise ValueError("The Admin / Master Portfolio is derived from the tracked-project register")

    portfolios = load_portfolios(settings)
    updated = {
        "portfolio_id": new_id,
        "portfolio_name": name.strip(),
        "description": description.strip(),
        "active": "Yes",
    }
    for index, row in enumerate(portfolios):
        if row["portfolio_id"] == new_id:
            portfolios[index] = updated
            break
    else:
        portfolios.append(updated)
    portfolios.sort(key=lambda row: (row["portfolio_id"] != MASTER_PORTFOLIO_ID, row["portfolio_name"].casefold()))
    atomic_write_csv(portfolios_path(settings), portfolios, list(PORTFOLIO_FIELDS))

    memberships = [
        row for row in load_portfolio_memberships(settings) if row["portfolio_id"] != new_id
    ]
    for code, project_set in project_sets.items():
        if project_set not in PROJECT_SETS:
            raise ValueError(f"Invalid project set for {code}: {project_set}")
        memberships.append(
            {
                "portfolio_id": new_id,
                "source_project_id": str(code),
                "project_set": project_set,
            }
        )
    memberships.sort(key=lambda row: (row["portfolio_id"], row["project_set"], row["source_project_id"]))
    atomic_write_csv(
        portfolio_memberships_path(settings), memberships, list(MEMBERSHIP_FIELDS)
    )
    return new_id


def assign_portfolio_projects(
    settings: Settings,
    *,
    portfolio_id: str,
    project_codes: list[str],
    project_set: str,
) -> None:
    if portfolio_id == MASTER_PORTFOLIO_ID:
        raise ValueError("Master project classifications belong to the tracked-project register")
    if project_set not in PROJECT_SETS:
        raise ValueError(f"Invalid project set: {project_set}")

    memberships = load_portfolio_memberships(settings)
    assignments = {
        (row["portfolio_id"], row["source_project_id"]): row
        for row in memberships
    }
    for code in project_codes:
        project_code = str(code).strip()
        if project_code:
            assignments[(portfolio_id, project_code)] = {
                "portfolio_id": portfolio_id,
                "source_project_id": project_code,
                "project_set": project_set,
            }
    updated = sorted(
        assignments.values(),
        key=lambda row: (row["portfolio_id"], row["project_set"], row["source_project_id"]),
    )
    atomic_write_csv(
        portfolio_memberships_path(settings), updated, list(MEMBERSHIP_FIELDS)
    )
