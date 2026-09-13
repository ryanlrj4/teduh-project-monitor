from __future__ import annotations

from pathlib import Path

import streamlit as st

from teduh_monitor.config import Settings, project_root
from teduh_monitor.monitor import alerts_path, current_metrics_path, history_csv_path
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

MONITOR_PAGES = ("My Portfolio", "Groups", "Compare", "Projects", "Alerts")
MANAGE_PAGES = (
    "Profiles",
    "Tracked projects",
    "Add or edit",
    "Discovery",
    "Refresh & data quality",
    "Audit log",
)
PAGE_BY_LABEL = {
    **{f"Monitor · {page}": page for page in MONITOR_PAGES},
    **{f"Manage · {page}": page for page in MANAGE_PAGES},
}
LABEL_BY_PAGE = {page: label for label, page in PAGE_BY_LABEL.items()}


def request_page(page: str) -> None:
    st.session_state["requested_page"] = page


def open_group(group_name: str) -> None:
    st.session_state["selected_group"] = group_name
    request_page("Groups")


st.set_page_config(page_title="Real Estate Project Monitor", page_icon="🏢", layout="wide")
st.markdown(STYLESHEET.read_text(encoding="utf-8"), unsafe_allow_html=True)
st.markdown(
    '<div class="app-kicker">Commercial Banking · Real Estate</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="app-title">Real Estate Project Monitor</div>',
    unsafe_allow_html=True,
)

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

if requested_page := st.session_state.pop("requested_page", None):
    st.session_state["active_page"] = LABEL_BY_PAGE[requested_page]
if st.session_state.get("active_page") not in PAGE_BY_LABEL:
    st.session_state["active_page"] = LABEL_BY_PAGE["My Portfolio"]

st.sidebar.markdown("### Directory")
page_label = st.sidebar.selectbox(
    "Page",
    list(PAGE_BY_LABEL),
    key="active_page",
)
page = PAGE_BY_LABEL[page_label]

if not profile_current.empty:
    searchable = profile_current.sort_values("display_name")
    search_labels = {
        str(row["source_project_id"]): str(
            row.get("display_name") or row.get("project_name") or row["source_project_id"]
        )
        for _, row in searchable.iterrows()
    }
    search_code = st.sidebar.selectbox(
        "Find a project",
        [""] + list(search_labels),
        format_func=lambda code: "Choose a project" if not code else search_labels[code],
        key=f"global_project_search_{selected_portfolio}",
    )
    if search_code and st.sidebar.button("Open project"):
        st.session_state["all_projects_name_search"] = search_labels[search_code]
        request_page("Projects")
        st.rerun()

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
    st.caption(
        "Turn this off to show the original Malay source wording. Official HIMS status terms such as Lancar, Sakit, Lewat and Siap Dengan CCC/CFO remain unchanged."
    )

if notice := st.session_state.pop("app_notice", None):
    st.success(notice)
if error := st.session_state.pop("app_error", None):
    st.error(error)

registry_name_by_code = {
    str(row.get("source_project_id") or ""): str(row.get("project_name") or "")
    for row in current_rows
}

if page == "My Portfolio":
    render_my_portfolio(
        profile_current,
        history,
        profile_alert_rows,
        portfolio_name=portfolio_names[selected_portfolio],
        on_view_group=open_group,
    )
elif page == "Groups":
    render_groups(
        profile_current,
        history,
        requested_group=st.session_state.pop("selected_group", None),
        on_view_group=open_group,
    )
elif page == "Compare":
    render_compare(profile_current, history, on_view_group=open_group)
elif page == "Projects":
    render_all_projects(profile_current, history, on_view_group=open_group)
elif page == "Alerts":
    render_alerts(profile_alert_rows, profile_shortlist_by_project)
elif page == "Profiles":
    render_profiles(
        SETTINGS,
        portfolios,
        memberships,
        shortlist_rows,
        registry_name_by_code,
    )
elif page == "Tracked projects":
    render_shortlist(
        SETTINGS,
        shortlist_rows,
        registry_name_by_code,
        include_refresh=False,
    )
elif page == "Add or edit":
    render_add_or_edit(SETTINGS, shortlist_rows, registry_name_by_code)
elif page == "Discovery":
    render_discovery(SETTINGS, shortlist_rows)
elif page == "Refresh & data quality":
    render_refresh_and_data_quality(SETTINGS)
elif page == "Audit log":
    render_audit_log(audit_rows, profile_shortlist_by_project, registry_name_by_code)

st.markdown(
    '<div class="creator-footer">Concept and prototype by Lim Ri Jun</div>',
    unsafe_allow_html=True,
)
