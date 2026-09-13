from pathlib import Path

import pandas as pd

from teduh_monitor.config import Settings
from teduh_monitor.portfolios import (
    assign_portfolio_projects,
    load_portfolio_memberships,
    load_portfolios,
    portfolio_current,
    portfolio_shortlist,
    save_portfolio,
)
from teduh_monitor.storage import write_csv


def shortlist_rows() -> list[dict[str, str]]:
    return [
        {"source_project_id": "1-1", "display_name": "One", "project_set": "reporting_set"},
        {"source_project_id": "2-1", "display_name": "Two", "project_set": "general"},
    ]


def test_master_portfolio_uses_all_tracked_projects(tmp_path: Path) -> None:
    settings = Settings(root=tmp_path)
    current = pd.DataFrame(shortlist_rows())
    assert len(portfolio_current(current, shortlist_rows(), [], "admin")) == 2
    assert len(portfolio_shortlist(shortlist_rows(), [], "admin")) == 2
    assert load_portfolios(settings)[0]["portfolio_id"] == "admin"


def test_save_and_load_profile_memberships(tmp_path: Path) -> None:
    settings = Settings(root=tmp_path)
    write_csv(
        tmp_path / "config" / "portfolios.csv",
        [
            {
                "portfolio_id": "admin",
                "portfolio_name": "Admin",
                "description": "Master",
                "active": "Yes",
            }
        ],
        ["portfolio_id", "portfolio_name", "description", "active"],
    )
    profile_id = save_portfolio(
        settings,
        portfolio_id=None,
        name="Test Profile",
        description="Focused review",
        project_sets={"1-1": "reporting_set", "2-1": "comparator_set"},
    )
    assert profile_id == "test_profile"
    memberships = load_portfolio_memberships(settings)
    current = pd.DataFrame(shortlist_rows())
    view = portfolio_current(current, shortlist_rows(), memberships, profile_id)
    assert set(view["source_project_id"]) == {"1-1", "2-1"}
    assert set(view["project_set"]) == {"reporting_set", "comparator_set"}


def test_assign_portfolio_projects_adds_and_reclassifies_memberships(tmp_path: Path) -> None:
    settings = Settings(root=tmp_path)
    write_csv(
        tmp_path / "config" / "portfolio_projects.csv",
        [
            {
                "portfolio_id": "test_profile",
                "source_project_id": "1-1",
                "project_set": "reporting_set",
            }
        ],
        ["portfolio_id", "source_project_id", "project_set"],
    )

    assign_portfolio_projects(
        settings,
        portfolio_id="test_profile",
        project_codes=["1-1", "2-1"],
        project_set="comparator_set",
    )

    memberships = load_portfolio_memberships(settings)
    assert memberships == [
        {
            "portfolio_id": "test_profile",
            "source_project_id": "1-1",
            "project_set": "comparator_set",
        },
        {
            "portfolio_id": "test_profile",
            "source_project_id": "2-1",
            "project_set": "comparator_set",
        },
    ]
