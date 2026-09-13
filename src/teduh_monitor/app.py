from __future__ import annotations

from pathlib import Path

import streamlit as st

from teduh_monitor.config import Settings, project_root
from teduh_monitor.monitor import (
    alerts_path,
    current_metrics_path,
    history_csv_path,
    refresh_projects,
)
from teduh_monitor.portfolios import (
    load_portfolio_memberships,
    load_portfolios,
    portfolio_current,
    portfolio_shortlist,
)
from teduh_monitor.shortlist import load_audit_log, load_shortlist
from teduh_monitor.ui.data import apply_shortlist_metadata, dataframe, read_csv
from teduh_monitor.ui.formatting import display_date, display_timestamp
from teduh_monitor.ui.pages import (
    render_add_or_edit,
    render_alerts,
    render_all_projects,
    render_audit_log,
    render_discovery,
    render_shortlist,
)
from teduh_monitor.ui.workspace_pages import (
    render_compare,
    render_groups,
    render_my_portfolio,
    render_profiles,
    render_refresh_and_data_quality,
)


ROOT = project_root()
SETTINGS = Settings(root=ROOT)
STYLESHEET = Path(__file__).with_name("ui") / "styles.css"


st.set_page_config(page_title="Real Estate Project Monitor", page_icon="🏢", layout="wide")
st.markdown(STYLESHEET.read_text(encoding="utf-8"), unsafe_allow_html=True)

shortlist_rows = load_shortlist(SETTINGS)
audit_rows = load_audit_log(SETTINGS)
current_rows = apply_shortlist_metadata(
    read_csv(current_metrics_path(SETTINGS)),
    shortlist_rows,
)
history_rows = read_csv(history_csv_path(SETTINGS))
alert_rows = read_csv(alerts_path(SETTINGS))
current = dataframe(current_rows)
history = dataframe(history_rows)
portfolios = [row for row in load_portfolios(SETTINGS) if row["active"] == "Yes"]
memberships = load_portfolio_memberships(SETTINGS)

portfolio_ids = [row["portfolio_id"] for row in portfolios]
portfolio_names = {row["portfolio_id"]: row["portfolio_name"] for row in portfolios}
if st.session_state.get("selected_portfolio") not in portfolio_ids:
    st.session_state["selected_portfolio"] = portfolio_ids[0]

st.sidebar.markdown("### Portfolio")
selected_portfolio = st.sidebar.selectbox(
    "Active profile",
    portfolio_ids,
    format_func=lambda value: portfolio_names[value],
    key="selected_portfolio",
)
profile_current = portfolio_current(current, shortlist_rows, memberships, selected_portfolio)
profile_shortlist = portfolio_shortlist(shortlist_rows, memberships, selected_portfolio)
profile_codes = {row["source_project_id"] for row in profile_shortlist}
profile_alert_rows = [
    row for row in alert_rows if str(row.get("source_project_id") or "") in profile_codes
]
profile_shortlist_by_project = {
    row["source_project_id"]: row for row in profile_shortlist
}
registry_name_by_code = {
    str(row.get("source_project_id") or ""): str(row.get("project_name") or "")
    for row in current_rows
}


def open_group(group_name: str) -> None:
    st.session_state["selected_group"] = group_name
    st.switch_page(groups_page)


def open_project(project_code: str) -> None:
    match = current[current["source_project_id"].astype(str) == str(project_code)]
    if not match.empty:
        row = match.iloc[0]
        st.session_state["all_projects_name_search"] = str(
            row.get("display_name") or row.get("project_name") or project_code
        )
    st.switch_page(projects_page)


def refresh_selected_projects(project_codes: list[str]) -> None:
    try:
        with st.spinner(f"Refreshing {len(project_codes):,} selected TEDUH project(s)…"):
            result = refresh_projects(
                SETTINGS,
                project_codes,
                progress=lambda _: None,
            )
        if result["project_count"]:
            message = f"Refreshed {result['project_count']:,} TEDUH project(s)."
        else:
            message = "No request sent; the selected project data was already refreshed today."
        previous_notice = st.session_state.get("app_notice")
        st.session_state["app_notice"] = (
            f"{previous_notice} {message}" if previous_notice else message
        )
    except Exception as exc:
        st.session_state["app_error"] = (
            f"Selected TEDUH refresh failed; previous valid metrics were preserved. {exc}"
        )


def refresh_project(project_code: str) -> None:
    refresh_selected_projects([project_code])


def show_my_portfolio() -> None:
    render_my_portfolio(
        profile_current,
        history,
        profile_alert_rows,
        portfolio_name=portfolio_names[selected_portfolio],
        on_view_group=open_group,
        on_refresh_project=refresh_project,
    )


def show_groups() -> None:
    render_groups(
        current,
        history,
        requested_group=st.session_state.pop("selected_group", None),
        on_view_group=open_group,
        on_refresh_project=refresh_project,
    )


def show_compare() -> None:
    render_compare(
        profile_current,
        current,
        settings=SETTINGS,
        active_portfolio_id=selected_portfolio,
        memberships=memberships,
        shortlist_rows=shortlist_rows,
        on_open_project=open_project,
        on_refresh_projects=refresh_selected_projects,
    )


def show_projects() -> None:
    render_all_projects(
        current,
        history,
        on_view_group=open_group,
        on_refresh_project=refresh_project,
    )


def show_alerts() -> None:
    render_alerts(profile_alert_rows, profile_shortlist_by_project)


def show_profiles() -> None:
    render_profiles(
        SETTINGS,
        portfolios,
        memberships,
        shortlist_rows,
        registry_name_by_code,
    )


def show_tracked_projects() -> None:
    render_shortlist(
        SETTINGS,
        shortlist_rows,
        registry_name_by_code,
        include_refresh=False,
        current_snapshot_by_code={
            str(row.get("source_project_id") or ""): str(row.get("snapshot_date") or "")
            for row in current_rows
        },
        on_refresh_project=refresh_project,
    )


def show_add_or_edit() -> None:
    render_add_or_edit(
        SETTINGS,
        shortlist_rows,
        registry_name_by_code,
        on_project_added=refresh_project,
    )


def show_discovery() -> None:
    render_discovery(
        SETTINGS,
        shortlist_rows,
        on_project_added=refresh_project,
    )


def show_refresh() -> None:
    render_refresh_and_data_quality(SETTINGS)


def show_audit_log() -> None:
    render_audit_log(audit_rows, profile_shortlist_by_project, registry_name_by_code)


my_portfolio_page = st.Page(
    show_my_portfolio,
    title="My Portfolio",
    icon=":material/home:",
    default=True,
)
groups_page = st.Page(show_groups, title="Groups", icon=":material/apartment:")
compare_page = st.Page(show_compare, title="Compare", icon=":material/compare_arrows:")
projects_page = st.Page(show_projects, title="Projects", icon=":material/search:")
alerts_page = st.Page(show_alerts, title="Alerts", icon=":material/notifications:")
profiles_page = st.Page(show_profiles, title="Profiles", icon=":material/person:")
tracked_projects_page = st.Page(
    show_tracked_projects,
    title="Tracked projects",
    icon=":material/list_alt:",
)
add_or_edit_page = st.Page(
    show_add_or_edit,
    title="Add or edit",
    icon=":material/edit:",
)
discovery_page = st.Page(show_discovery, title="Discovery", icon=":material/travel_explore:")
refresh_page = st.Page(
    show_refresh,
    title="Refresh & data quality",
    icon=":material/sync:",
)
audit_page = st.Page(show_audit_log, title="Audit log", icon=":material/history:")

navigation = st.navigation(
    {
        "Monitor": [
            my_portfolio_page,
            groups_page,
            compare_page,
            projects_page,
            alerts_page,
        ],
        "Manage": [
            profiles_page,
            tracked_projects_page,
            add_or_edit_page,
            discovery_page,
            refresh_page,
            audit_page,
        ],
    },
    expanded=True,
)

if not current.empty:
    st.sidebar.divider()
    st.sidebar.markdown("### Find a project")
    project_query = st.sidebar.text_input(
        "Project search",
        placeholder="Name, code, group or developer",
        key=f"global_project_search_{selected_portfolio}",
        label_visibility="collapsed",
    )
    if project_query.strip():
        needle = project_query.strip().casefold()
        searchable = current.copy()
        search_columns = [
            "source_project_id",
            "display_name",
            "project_name",
            "parent_group",
            "developer_name",
        ]
        matches = searchable[
            searchable[search_columns]
            .fillna("")
            .apply(lambda row: needle in " ".join(row.astype(str)).casefold(), axis=1)
        ].sort_values("display_name")
        if matches.empty:
            st.sidebar.caption("No matching projects")
        for _, row in matches.head(6).iterrows():
            code = str(row["source_project_id"])
            label = str(row.get("display_name") or row.get("project_name") or code)
            if st.sidebar.button(
                f"{label} · {code}",
                key=f"global_project_result_{code}",
                width="stretch",
            ):
                open_project(code)

st.markdown(
    '<div class="app-kicker">Commercial Banking · Real Estate</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="app-title">Real Estate Project Monitor</div>',
    unsafe_allow_html=True,
)
last_retrieved = max((row.get("retrieved_at", "") for row in current_rows), default="")
source_as_of = max((row.get("source_dataset_as_of", "") for row in current_rows), default="")
st.markdown(
    f'<div class="source-note"><b>Source:</b> TEDUH public API · '
    f'<b>Retrieved:</b> {display_timestamp(last_retrieved)} · '
    f'<b>TEDUH displayed data through:</b> {display_date(source_as_of)}</div>',
    unsafe_allow_html=True,
)

with st.popover("Settings"):
    st.markdown("**TEDUH display language**")
    st.toggle(
        "Translate TEDUH values to English",
        value=True,
        key="translate_teduh_values",
    )

if notice := st.session_state.pop("app_notice", None):
    st.success(notice)
if error := st.session_state.pop("app_error", None):
    st.error(error)

navigation.run()

st.markdown(
    '<div class="creator-footer">Concept and prototype by Lim Ri Jun</div>',
    unsafe_allow_html=True,
)
