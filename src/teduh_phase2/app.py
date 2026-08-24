from __future__ import annotations

from pathlib import Path

import streamlit as st

from teduh_phase2.config import Settings, project_root
from teduh_phase2.monitor import alerts_path, current_metrics_path, history_csv_path
from teduh_phase2.shortlist import load_audit_log, load_shortlist
from teduh_phase2.ui.data import apply_shortlist_metadata, dataframe, read_csv
from teduh_phase2.ui.formatting import display_date, display_timestamp
from teduh_phase2.ui.pages import (
    render_add_or_edit,
    render_alerts,
    render_all_projects,
    render_audit_log,
    render_discovery,
    render_overview,
    render_shortlist,
)


ROOT = project_root()
SETTINGS = Settings(root=ROOT)
STYLESHEET = Path(__file__).with_name("ui") / "styles.css"


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
shortlist_by_project = {
    row["source_project_id"]: row
    for row in shortlist_rows
}
registry_name_by_code = {
    str(row.get("source_project_id") or ""): str(row.get("project_name") or "")
    for row in current_rows
}
active_shortlist = [
    row
    for row in shortlist_rows
    if row["active"] == "Yes"
]

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

app_notice = st.session_state.pop("app_notice", None)
if app_notice:
    st.success(app_notice)
app_error = st.session_state.pop("app_error", None)
if app_error:
    st.error(app_error)

overview_tab, all_projects_tab, shortlist_tab, add_tab, discovery_tab, alerts_tab, audit_tab = st.tabs(
    ["Overview", "All projects", "Shortlist", "Add or edit", "Discovery", "Alerts", "Audit log"]
)

with overview_tab:
    render_overview(current, history, active_shortlist)
with all_projects_tab:
    render_all_projects(current, history)
with shortlist_tab:
    render_shortlist(SETTINGS, shortlist_rows, registry_name_by_code)
with add_tab:
    render_add_or_edit(SETTINGS, shortlist_rows, registry_name_by_code)
with discovery_tab:
    render_discovery(SETTINGS, shortlist_rows)
with alerts_tab:
    render_alerts(alert_rows, shortlist_by_project)
with audit_tab:
    render_audit_log(audit_rows, shortlist_by_project, registry_name_by_code)

st.markdown(
    '<div class="creator-footer">Concept and prototype by Lim Ri Jun</div>',
    unsafe_allow_html=True,
)
