from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from teduh_phase2.config import DEFAULT_REGION, REGION_CONFIGS, Settings, project_root
from teduh_phase2.discovery import (
    discovery_manifest_path,
    load_discovery_catalog,
    run_discovery,
)
from teduh_phase2.monitor import (
    alerts_path,
    current_metrics_path,
    history_csv_path,
    snapshot_shortlist,
)
from teduh_phase2.metrics import component_completion_dates
from teduh_phase2.shortlist import (
    PROJECT_SETS,
    PRIORITIES,
    load_audit_log,
    load_shortlist,
    upsert_shortlist_project,
)


ROOT = project_root()
SETTINGS = Settings(root=ROOT)
SET_LABELS = {
    "reporting_set": "Reporting Set",
    "comparator_set": "Comparator Set",
    "general": "General",
}
REGION_LABELS = {
    "Kuala Lumpur": "KL",
}


st.set_page_config(page_title="Real Estate Project Monitor", page_icon="🏢", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap');

    :root {
        --ocbc-red: #E30613;
        --ocbc-red-dark: #C9000B;
        --ocbc-white: #FFFFFF;
        --ocbc-charcoal: #363B40;
        --ocbc-muted: #666B70;
        --ocbc-surface: #F6F6F6;
        --ocbc-border: #DEDEDE;
    }

    html, body, [class*="st-"], [data-testid="stAppViewContainer"] {
        font-family: "Open Sans", OpenSans, Helvetica, Arial, sans-serif;
        color: var(--ocbc-charcoal);
    }
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background: var(--ocbc-white);
    }
    [data-testid="stHeader"] {
        background: rgba(255,255,255,.96);
        border-bottom: 1px solid #EEEEEE;
    }
    .block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
    h1, h2, h3, h4, h5, h6 {
        color: var(--ocbc-charcoal);
        font-family: "Open Sans", OpenSans, Helvetica, Arial, sans-serif;
        letter-spacing: -.015em;
    }
    p, label, [data-testid="stCaptionContainer"] {color: var(--ocbc-charcoal);}
    a {color: var(--ocbc-red);}

    [data-testid="stMetric"] {
        background: var(--ocbc-white);
        border: 1px solid var(--ocbc-border);
        border-top: 4px solid var(--ocbc-red);
        border-radius: 5px;
        padding: 14px;
        box-shadow: 0 1px 3px rgba(54,59,64,.06);
    }
    [data-testid="stMetricLabel"] {color: var(--ocbc-muted) !important;font-weight:600;}
    [data-testid="stMetricValue"] {color: var(--ocbc-charcoal) !important;font-weight:600;}
    .st-key-project_detail_panel [data-testid="stMetric"] {
        border-top-width: 2px;
        padding: 10px 12px;
        min-height: 0;
    }
    .st-key-project_detail_panel [data-testid="stMetricLabel"] p {
        font-size: .78rem !important;
        line-height: 1.2 !important;
    }
    .st-key-project_detail_panel [data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        line-height: 1.3 !important;
    }
    .st-key-manual_project_details {
        background: var(--ocbc-surface);
        border-left: 4px solid var(--ocbc-muted);
        border-radius: 5px;
        padding: .75rem 1rem .4rem;
        margin: .65rem 0 1rem;
    }
    .st-key-manual_project_details [data-testid="stMetric"] {
        background: var(--ocbc-white);
        border-top-color: var(--ocbc-muted);
    }

    div.stButton button, div.stDownloadButton button, [data-testid="stFormSubmitButton"] button {
        min-height: 2.7rem;
        border: 1px solid var(--ocbc-red);
        border-radius: 5px !important;
        color: var(--ocbc-red);
        background: var(--ocbc-white);
        font-family: "Open Sans", OpenSans, Helvetica, Arial, sans-serif;
        font-weight: 600;
    }
    div.stButton button p, div.stDownloadButton button p, [data-testid="stFormSubmitButton"] button p {
        color: inherit;
        font-weight: 600;
    }
    div.stButton button:hover, div.stDownloadButton button:hover, [data-testid="stFormSubmitButton"] button:hover {
        border-color: var(--ocbc-red-dark);
        color: var(--ocbc-red-dark);
        background: #FFF5F5;
    }
    div.stButton button[kind="primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"] {
        color: var(--ocbc-white) !important;
        background: var(--ocbc-red) !important;
        border-color: var(--ocbc-red) !important;
    }
    div.stButton button[kind="primary"] p,
    [data-testid="stFormSubmitButton"] button[kind="primary"] p {
        color: var(--ocbc-white) !important;
    }
    div.stButton button[kind="primary"]:hover,
    [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
        color: var(--ocbc-white) !important;
        background: var(--ocbc-red-dark) !important;
        border-color: var(--ocbc-red-dark) !important;
    }

    [data-baseweb="tab-list"] {
        border-bottom: 1px solid var(--ocbc-border);
        gap: .5rem;
    }
    [data-baseweb="tab"] {
        color: var(--ocbc-muted);
        font-family: "Open Sans", OpenSans, Helvetica, Arial, sans-serif;
        font-weight: 600;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    [data-baseweb="tab"] p {color: inherit;font-weight:600;}
    [data-baseweb="tab"][aria-selected="true"] {color: var(--ocbc-red);}

    [data-baseweb="input"], [data-baseweb="select"] > div,
    [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {
        border-color: var(--ocbc-border);
        border-radius: 5px;
        background: var(--ocbc-white);
    }
    [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within,
    [data-testid="stTextArea"] textarea:focus, [data-testid="stNumberInput"] input:focus {
        border-color: var(--ocbc-red);
        box-shadow: 0 0 0 1px var(--ocbc-red);
    }
    [data-testid="stDataFrame"] {
        border: 1px solid var(--ocbc-border);
        border-radius: 5px;
        overflow: hidden;
    }

    .app-kicker {
        color: var(--ocbc-red);
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .09em;
        text-transform: uppercase;
    }
    .app-title {
        color: var(--ocbc-charcoal);
        font-size: 2.15rem;
        font-weight: 600;
        line-height: 1.2;
        margin: .3rem 0 1rem;
        border-left: 6px solid var(--ocbc-red);
        padding-left: .8rem;
    }
    .source-note {
        background: #FFF5F5;
        border-left: 4px solid var(--ocbc-red);
        padding: .7rem .9rem;
        border-radius: 5px;
        color: var(--ocbc-charcoal);
    }
    .creator-footer {
        border-top: 1px solid var(--ocbc-border);
        color: var(--ocbc-muted);
        font-size: .72rem;
        margin-top: 2.5rem;
        padding-top: .75rem;
        text-align: right;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def money(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "—"
    return f"RM {float(value):,.0f}"


def numeric_range(
    minimum: object,
    maximum: object,
    *,
    prefix: str = "",
    suffix: str = "",
    decimals: int = 0,
) -> str:
    if minimum in (None, "") or maximum in (None, "") or pd.isna(minimum) or pd.isna(maximum):
        return "—"
    low = float(minimum)
    high = float(maximum)
    formatter = f",.{decimals}f"
    if round(low, decimals) == round(high, decimals):
        return f"{prefix}{format(low, formatter)}{suffix}"
    return f"{prefix}{format(low, formatter)}–{format(high, formatter)}{suffix}"


def whole_number(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "—"
    return f"{int(float(value)):,}"


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def display_date(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "—"
    parsed = pd.to_datetime(value, errors="coerce")
    return "—" if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def display_timestamp(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.strftime("%d %b %Y, %I:%M %p")


def region_label(value: object) -> str:
    text = str(value or "—")
    return REGION_LABELS.get(text, text)


def dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if not frame.empty and "region" not in frame.columns:
        frame["region"] = DEFAULT_REGION
    if not frame.empty:
        for field in ("ccc_date", "vp_date"):
            if field not in frame.columns:
                frame[field] = None
        if "construction_rows_json" in frame.columns:
            for index, raw_rows in frame["construction_rows_json"].items():
                if (
                    frame.at[index, "ccc_date"] not in (None, "")
                    and frame.at[index, "vp_date"] not in (None, "")
                ):
                    continue
                try:
                    ccc_date, vp_date = component_completion_dates(json.loads(raw_rows or "[]"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if frame.at[index, "ccc_date"] in (None, ""):
                    frame.at[index, "ccc_date"] = ccc_date
                if frame.at[index, "vp_date"] in (None, ""):
                    frame.at[index, "vp_date"] = vp_date
    for column in (
        "reported_total_units",
        "sold_units",
        "comparable_total_units",
        "sales_percentage",
        "construction_percentage",
        "manual_built_up_min_sqft",
        "manual_built_up_max_sqft",
        "manual_psf_min",
        "manual_psf_max",
        "teduh_spa_price_min",
        "teduh_spa_price_max",
        "potential_listed_gdv",
        "recorded_spa_sales_value",
        "estimated_sold_value",
        "remaining_listed_value",
        "unit_coverage_percentage",
        "listed_price_coverage_percentage",
        "spa_price_coverage_percentage",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


st.markdown('<div class="app-kicker">Commercial Banking · Real Estate</div>', unsafe_allow_html=True)
st.markdown('<div class="app-title">Real Estate Project Monitor</div>', unsafe_allow_html=True)

shortlist_rows = load_shortlist(SETTINGS)
audit_rows = load_audit_log(SETTINGS)
current_rows = read_csv(current_metrics_path(SETTINGS))
shortlist_by_project = {row["source_project_id"]: row for row in shortlist_rows}
for current_row in current_rows:
    tracked = shortlist_by_project.get(str(current_row.get("source_project_id") or ""))
    if not tracked:
        continue
    for field in (
        "region",
        "display_name",
        "parent_group",
        "project_set",
        "manual_launch_date",
        "manual_built_up_min_sqft",
        "manual_built_up_max_sqft",
        "manual_psf_min",
        "manual_psf_max",
        "priority",
        "tracking_notes",
    ):
        current_row[field] = tracked.get(field, "")
history_rows = read_csv(history_csv_path(SETTINGS))
alert_rows = read_csv(alerts_path(SETTINGS))
current = dataframe(current_rows)
history = dataframe(history_rows)
registry_name_by_code = {
    str(row.get("source_project_id") or ""): str(row.get("project_name") or "")
    for row in current_rows
}
active_shortlist = [row for row in shortlist_rows if row["active"] == "Yes"]
last_retrieved = max((row.get("retrieved_at", "") for row in current_rows), default="")
source_as_of = max((row.get("source_dataset_as_of", "") for row in current_rows), default="")
st.markdown(
    f'<div class="source-note"><b>Source:</b> TEDUH public API · '
    f'<b>Retrieved:</b> {display_timestamp(last_retrieved)} · '
    f'<b>TEDUH displayed data through:</b> {display_date(source_as_of)}</div>',
    unsafe_allow_html=True,
)
app_notice = st.session_state.pop("app_notice", None)
if app_notice:
    st.success(app_notice)

overview_tab, shortlist_tab, add_tab, discovery_tab, alerts_tab, audit_tab = st.tabs(
    ["Overview", "Shortlist", "Add or edit", "Discovery", "Alerts", "Audit log"]
)

with overview_tab:
    if current.empty:
        st.info("The authorized starter shortlist is ready. Run the first shortlist refresh to populate TEDUH metrics.")
        st.caption(f"Tracking {len(active_shortlist):,} projects")
    else:
        observed_regions = set(current["region"].dropna().astype(str))
        region_options = ["All regions"] + [
            region for region in REGION_CONFIGS if region in observed_regions
        ]
        selected_region = st.radio(
            "Region",
            region_options,
            horizontal=True,
            key="overview_region",
            format_func=region_label,
        )
        view = (
            current
            if selected_region == "All regions"
            else current[current["region"] == selected_region]
        )
        st.caption(f"Tracking {len(view):,} projects")
        risk_mask = view["project_status"].fillna("").str.casefold().str.contains("sakit|lewat|batal")

        st.subheader("Projects needing attention")
        risk_columns = ["display_name", "parent_group", "project_status", "sales_percentage", "construction_percentage"]
        if selected_region == "All regions":
            risk_columns.insert(1, "region")
        risk = view.loc[
            risk_mask,
            risk_columns,
        ].copy()
        if "region" in risk.columns:
            risk["region"] = risk["region"].map(region_label)
        if risk.empty:
            st.success("No current Sakit, Lewat or cancelled statuses.")
        else:
            st.dataframe(
                risk,
                hide_index=True,
                width="stretch",
                column_config={
                    "display_name": "Project",
                    "region": "Region",
                    "parent_group": "Parent group",
                    "project_status": "Status",
                    "sales_percentage": st.column_config.NumberColumn("Sales", format="%.1f%%"),
                    "construction_percentage": st.column_config.NumberColumn("Construction", format="%.1f%%"),
                },
            )

        st.subheader("Current shortlist snapshot")
        st.caption("Select one project row to open its financial and source details.")
        snapshot = view.copy().reset_index(drop=True)
        snapshot["developer_or_parent_group"] = snapshot.apply(
            lambda row: row.get("parent_group") or row.get("developer_name") or "—",
            axis=1,
        )
        snapshot["sold_display"] = snapshot["sold_units"].map(whole_number)
        snapshot["units_display"] = snapshot["reported_total_units"].map(whole_number)
        snapshot["potential_gdv_display"] = snapshot["potential_listed_gdv"].map(money)
        snapshot["region_display"] = snapshot["region"].map(region_label)
        snapshot["project_set_display"] = (
            snapshot["project_set"].map(SET_LABELS).fillna(snapshot["project_set"])
        )
        overview_columns = [
            "display_name",
            "developer_or_parent_group",
            "region_display",
            "project_status",
            "sold_display",
            "units_display",
            "sales_percentage",
            "construction_percentage",
            "potential_gdv_display",
            "project_set_display",
        ]
        snapshot_event = st.dataframe(
            snapshot[overview_columns],
            hide_index=True,
            width="stretch",
            key=f"current_shortlist_snapshot_{selected_region}",
            on_select="rerun",
            selection_mode="single-row",
            selection_default={"selection": {"rows": [0]}},
            column_config={
                "display_name": "Project",
                "region_display": "Region",
                "developer_or_parent_group": "Parent group / developer",
                "project_set_display": "Project set",
                "project_status": "TEDUH status",
                "sold_display": "Sold",
                "units_display": "Units",
                "sales_percentage": st.column_config.ProgressColumn("Sales", min_value=0, max_value=100, format="%.1f%%"),
                "construction_percentage": st.column_config.ProgressColumn("Construction", min_value=0, max_value=100, format="%.1f%%"),
                "potential_gdv_display": "Potential GDV",
            },
        )
        selected_rows = snapshot_event.selection.rows
        if selected_rows:
            selected = snapshot.iloc[selected_rows[0]]
            preferred_name = str(selected.get("display_name") or selected.get("project_name") or selected.get("source_project_id"))
            teduh_name = str(selected.get("project_name") or "")
            parent_group = str(selected.get("parent_group") or "")
            registered_developer = str(selected.get("developer_name") or "—")

            st.markdown(f"### {preferred_name}")
            if teduh_name and teduh_name.casefold() != preferred_name.casefold():
                st.caption(f"TEDUH registered name: {teduh_name}")

            with st.container(border=True, key="project_detail_panel"):
                identity_region, identity_left, identity_middle, identity_right = st.columns(4)
                identity_region.markdown("**Region**")
                identity_region.write(region_label(selected.get("region")))
                identity_left.markdown("**Parent group**")
                identity_left.write(parent_group or "Not mapped")
                identity_middle.markdown("**Registered developer / SPV**")
                identity_middle.write(registered_developer)
                identity_right.markdown("**TEDUH project code**")
                identity_right.write(str(selected.get("source_project_id") or "—"))

                st.markdown("#### TEDUH project information")
                market_details = st.columns(2)
                market_details[0].metric("First SPA", display_date(selected.get("first_spa_date")))
                market_details[1].metric(
                    "SPA price range",
                    numeric_range(
                        selected.get("teduh_spa_price_min"),
                        selected.get("teduh_spa_price_max"),
                        prefix="RM ",
                    ),
                )
                st.caption(
                    "SPA price range uses the minimum and maximum prices displayed in TEDUH's component-status table."
                )

                has_manual_launch = bool(str(selected.get("manual_launch_date") or "").strip())
                has_manual_built_up = pd.notna(selected.get("manual_built_up_min_sqft")) and pd.notna(
                    selected.get("manual_built_up_max_sqft")
                )
                has_manual_psf = pd.notna(selected.get("manual_psf_min")) and pd.notna(
                    selected.get("manual_psf_max")
                )
                if has_manual_launch or has_manual_built_up or has_manual_psf:
                    with st.container(key="manual_project_details"):
                        st.markdown("#### Locally entered supplementary details")
                        st.caption(
                            "Only the fields inside this grey section were entered locally; they do not come from TEDUH."
                        )
                        manual_columns = st.columns(
                            int(has_manual_launch) + int(has_manual_built_up) + int(has_manual_psf)
                        )
                        manual_index = 0
                        if has_manual_launch:
                            manual_columns[manual_index].metric(
                                "Launch date", display_date(selected.get("manual_launch_date"))
                            )
                            manual_index += 1
                        if has_manual_built_up:
                            manual_columns[manual_index].metric(
                                "Built-up range",
                                numeric_range(
                                    selected.get("manual_built_up_min_sqft"),
                                    selected.get("manual_built_up_max_sqft"),
                                    suffix=" sqft",
                                ),
                            )
                            manual_index += 1
                        if has_manual_psf:
                            manual_columns[manual_index].metric(
                                "PSF range",
                                numeric_range(
                                    selected.get("manual_psf_min"),
                                    selected.get("manual_psf_max"),
                                    prefix="RM ",
                                    suffix="/sqft",
                                ),
                            )

                st.markdown("#### Current monitoring metrics")
                st.caption(
                    "The figures below come from the current TEDUH snapshot or are calculated from its unit and component data."
                )

                value_top = st.columns(2)
                value_top[0].metric("Potential listed GDV", money(selected.get("potential_listed_gdv")))
                value_top[1].metric("Estimated value sold", money(selected.get("estimated_sold_value")))
                value_bottom = st.columns(2)
                value_bottom[0].metric("Recorded SPA value", money(selected.get("recorded_spa_sales_value")))
                value_bottom[1].metric("Remaining listed value", money(selected.get("remaining_listed_value")))

                progress_columns = st.columns(4)
                progress_columns[0].metric(
                    "Units sold",
                    f"{whole_number(selected.get('sold_units'))} / {whole_number(selected.get('reported_total_units'))}",
                )
                progress_columns[1].metric("Calculated sales", pct(selected.get("sales_percentage")))
                progress_columns[2].metric("Construction", pct(selected.get("construction_percentage")))
                progress_columns[3].metric("CCC/CFO obtained", str(selected.get("ccc_obtained") or "—"))

                if str(selected.get("ccc_obtained") or "") == "Yes":
                    completion_columns = st.columns(2)
                    completion_columns[0].metric(
                        "CCC/CFO date", display_date(selected.get("ccc_date"))
                    )
                    completion_columns[1].metric("VP date", display_date(selected.get("vp_date")))
                    st.caption(
                        "Completion dates are the latest valid component dates displayed by TEDUH; a dash means TEDUH does not provide one."
                    )

                st.caption(
                    "Estimated value sold uses recorded SPA prices where available and listed-price fallback otherwise. "
                    "Potential GDV and remaining value are analytical listed-price measures, not audited developer figures."
                )

                st.markdown("#### Data timing")
                timing = st.columns(2)
                timing[0].metric("Retrieved from TEDUH", display_timestamp(selected.get("retrieved_at")))
                timing[1].metric("TEDUH displayed data through", display_date(selected.get("source_dataset_as_of")))
                st.caption(
                    "The retrieval time is recorded by this application. TEDUH's displayed data-through date is a "
                    "frontend label and is not an authoritative per-project API update timestamp."
                )

                st.markdown("#### Weekly progress trend")
                project_history = history[
                    history["source_project_id"].astype(str) == str(selected.get("source_project_id"))
                ].copy() if not history.empty else pd.DataFrame()
                if project_history.empty:
                    st.info("No dated observations have been stored for this project yet.")
                else:
                    project_history["observation_date"] = pd.to_datetime(
                        project_history["snapshot_date"], errors="coerce"
                    )
                    project_history = project_history.dropna(subset=["observation_date"]).sort_values(
                        ["observation_date", "retrieved_at"]
                    )
                    project_history["week_start"] = (
                        project_history["observation_date"]
                        - pd.to_timedelta(project_history["observation_date"].dt.weekday, unit="D")
                    )
                    weekly = project_history.groupby("week_start", as_index=False).tail(1).copy()
                    weekly = weekly.sort_values("week_start")
                    weekly["Week"] = weekly["week_start"].dt.strftime("%d %b %Y")
                    weekly["Units sold"] = weekly["sold_units"]
                    weekly["Weekly units sold"] = weekly["sold_units"].diff()
                    weekly["Sales %"] = weekly["sales_percentage"]
                    weekly["Sales change"] = weekly["sales_percentage"].diff()
                    weekly["Construction %"] = weekly["construction_percentage"]
                    weekly["Construction change"] = weekly["construction_percentage"].diff()
                    weekly["Status"] = weekly["project_status"]

                    if len(weekly) == 1:
                        st.info(
                            "This is the opening observation. Week-on-week changes will appear after the next weekly refresh; "
                            "past sales dates cannot be reconstructed from TEDUH's current snapshot."
                        )
                    chart = weekly.set_index("week_start")[["Sales %", "Construction %"]]
                    st.line_chart(chart, height=260)
                    st.dataframe(
                        weekly[
                            [
                                "Week",
                                "Units sold",
                                "Weekly units sold",
                                "Sales %",
                                "Sales change",
                                "Construction %",
                                "Construction change",
                                "Status",
                            ]
                        ],
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "Units sold": st.column_config.NumberColumn(format="%d"),
                            "Weekly units sold": st.column_config.NumberColumn(format="%+d"),
                            "Sales %": st.column_config.NumberColumn(format="%.1f%%"),
                            "Sales change": st.column_config.NumberColumn(format="%+.1f pp"),
                            "Construction %": st.column_config.NumberColumn(format="%.1f%%"),
                            "Construction change": st.column_config.NumberColumn(format="%+.1f pp"),
                        },
                    )

with shortlist_tab:
    st.subheader("Saved projects")
    st.caption(
        "The display name, parent group, project set and notes are yours to edit. "
        "The weekly collection target is Monday, and manual refresh remains available."
    )

    shortlist_frame = pd.DataFrame(shortlist_rows)
    if shortlist_frame.empty:
        st.warning("No shortlist projects have been added.")
    else:
        watch_regions = ["All regions"] + list(REGION_CONFIGS)
        watch_region = st.radio(
            "Region",
            watch_regions,
            horizontal=True,
            key="shortlist_region",
            format_func=region_label,
        )
        if watch_region != "All regions":
            shortlist_frame = shortlist_frame[shortlist_frame["region"] == watch_region]
        shortlist_frame["project_set"] = shortlist_frame["project_set"].map(SET_LABELS).fillna(shortlist_frame["project_set"])
        shortlist_frame["region_display"] = shortlist_frame["region"].map(region_label)
        shortlist_frame["display_name"] = shortlist_frame.apply(
            lambda row: row["display_name"]
            or registry_name_by_code.get(str(row["source_project_id"]), "")
            or "TEDUH name will appear after refresh",
            axis=1,
        )
        st.dataframe(
            shortlist_frame[
                ["source_project_id", "region_display", "display_name", "parent_group", "project_set", "priority", "active", "tracking_notes"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "source_project_id": "TEDUH code",
                "region_display": "Region",
                "display_name": "Display name (local or TEDUH)",
                "parent_group": "Parent group",
                "project_set": "Project set",
                "priority": "Priority",
                "active": "Active",
                "tracking_notes": "Your notes",
            },
        )
    st.divider()
    refresh_spacer, refresh_action = st.columns([3, 1])
    with refresh_action:
        refresh_clicked = st.button("Refresh TEDUH shortlist", type="primary", width="stretch")
    if refresh_clicked:
        progress_messages: list[str] = []
        try:
            with st.spinner("Refreshing active projects sequentially from TEDUH…"):
                result = snapshot_shortlist(SETTINGS, progress=progress_messages.append)
            st.session_state["app_notice"] = (
                f"Refresh completed: {result['project_count']} projects and {result['alert_count']} alerts."
            )
            st.rerun()
        except Exception as exc:  # Streamlit must surface source failures without replacing valid output.
            st.error(str(exc))
            if progress_messages:
                st.caption(progress_messages[-1])

with add_tab:
    st.subheader("Add or edit a tracked project")
    mode = st.radio("Action", ["Add new", "Edit existing"], horizontal=True)
    existing_by_code = {row["source_project_id"]: row for row in shortlist_rows}
    selected_existing: dict[str, str] | None = None
    if mode == "Edit existing" and existing_by_code:
        chosen = st.selectbox(
            "Project",
            list(existing_by_code),
            format_func=lambda code: (
                f"{existing_by_code[code]['display_name'] or registry_name_by_code.get(code) or 'TEDUH project'} · {code}"
            ),
        )
        selected_existing = existing_by_code[chosen]
    default = selected_existing or {}
    with st.form("shortlist_project_form"):
        code = st.text_input("TEDUH project code", value=default.get("source_project_id", ""), disabled=bool(selected_existing))
        first, second = st.columns(2)
        display_name = first.text_input(
            "Actual/display project name (optional)",
            value=default.get("display_name", ""),
            placeholder="Leave blank to use TEDUH's registered name",
            help="Only enter this when your team uses a clearer or more familiar project name.",
        )
        parent_group = second.text_input("Parent group", value=default.get("parent_group", ""))
        third, fourth, fifth = st.columns(3)
        region = third.selectbox(
            "Region",
            list(REGION_CONFIGS),
            index=list(REGION_CONFIGS).index(default.get("region", DEFAULT_REGION)),
            format_func=region_label,
        )
        project_set = fourth.selectbox(
            "Project set",
            list(PROJECT_SETS),
            index=list(PROJECT_SETS).index(default.get("project_set", "general")),
            format_func=lambda value: SET_LABELS[value],
        )
        priority = fifth.selectbox(
            "Priority",
            list(PRIORITIES),
            index=list(PRIORITIES).index(default.get("priority", "medium")),
        )
        st.markdown("**Optional manually entered project details**")
        st.caption(
            "Leave these blank to hide them from project details. Use YYYY-MM-DD for the optional launch date."
        )
        manual_launch_date = st.text_input(
            "Launch date (optional)",
            value=default.get("manual_launch_date", ""),
            placeholder="YYYY-MM-DD",
            help="This is your manually sourced launch date and remains separate from TEDUH's First SPA date.",
        )
        manual_area_min, manual_area_max, manual_psf_low, manual_psf_high = st.columns(4)
        built_up_min = manual_area_min.text_input(
            "Built-up minimum (sqft)", value=default.get("manual_built_up_min_sqft", "")
        )
        built_up_max = manual_area_max.text_input(
            "Built-up maximum (sqft)", value=default.get("manual_built_up_max_sqft", "")
        )
        psf_min = manual_psf_low.text_input(
            "PSF minimum (RM/sqft)", value=default.get("manual_psf_min", "")
        )
        psf_max = manual_psf_high.text_input(
            "PSF maximum (RM/sqft)", value=default.get("manual_psf_max", "")
        )
        notes = st.text_area("Your monitoring notes", value=default.get("tracking_notes", ""), help="This is your own internal note; no CHGP analyst notes are imported.")
        active = st.checkbox("Actively refresh this project", value=default.get("active", "Yes") == "Yes")
        changed_by = st.text_input(
            "Changed by (name or initials)",
            value=st.session_state.get("audit_actor", ""),
            key="project_changed_by",
            help="Required for the audit log. Initials are sufficient for this local prototype.",
        )
        submitted = st.form_submit_button("Save project", type="primary")
    if submitted:
        if not changed_by.strip():
            st.error("Enter your name or initials so this change can be recorded in the audit log.")
        else:
            try:
                upsert_shortlist_project(
                    SETTINGS,
                    {
                        "source_project_id": code,
                        "region": region,
                        "display_name": display_name,
                        "parent_group": parent_group,
                        "project_set": project_set,
                        "manual_launch_date": manual_launch_date,
                        "manual_built_up_min_sqft": built_up_min,
                        "manual_built_up_max_sqft": built_up_max,
                        "manual_psf_min": psf_min,
                        "manual_psf_max": psf_max,
                        "priority": priority,
                        "tracking_notes": notes,
                        "active": "Yes" if active else "No",
                        "date_added": default.get("date_added", ""),
                        "origin": default.get("origin", "manual"),
                    },
                    changed_by=changed_by,
                )
                st.session_state["audit_actor"] = changed_by.strip()
                st.session_state["app_notice"] = (
                    f"Saved TEDUH project {code}. "
                    + (
                        f'The dashboard will show your name “{display_name}”.'
                        if display_name.strip()
                        else "TEDUH's registered project name will be used after refresh."
                    )
                    + " Manual fields appear immediately; refresh the shortlist only when you want current TEDUH metrics."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

with discovery_tab:
    st.subheader("On-demand regional discovery")
    st.caption("Discovery can make at most one live catalogue request set per region each day. A second run reuses that region's same-day cache.")
    discovery_region = st.selectbox(
        "Region", list(REGION_CONFIGS), key="discovery_region", format_func=region_label
    )
    manifest_path = discovery_manifest_path(SETTINGS, discovery_region)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        st.info(f"Last discovery: {manifest.get('discovery_date')} · {manifest.get('project_count', 0):,} catalogue projects")
    if st.button("Run Discovery", type="primary"):
        messages: list[str] = []
        try:
            with st.spinner(f"Reviewing the {discovery_region} TEDUH catalogue…"):
                result = run_discovery(
                    SETTINGS,
                    region=discovery_region,
                    progress=messages.append,
                )
            action = "Live discovery completed" if result["live_request_performed"] else "Same-day discovery cache reused"
            st.session_state["app_notice"] = f"{action}: {result['project_count']:,} projects."
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    discovery_rows = load_discovery_catalog(SETTINGS, discovery_region)
    if discovery_rows:
        discovery = pd.DataFrame(discovery_rows)
        tracked_codes = {row["source_project_id"] for row in shortlist_rows}
        discovery["currently_tracked"] = discovery["source_project_id"].isin(tracked_codes).map({True: "Yes", False: "No"})
        search = st.text_input("Search project, developer or TEDUH code", key="discovery_search")
        status_values = sorted(value for value in discovery["project_status"].dropna().unique() if value)
        statuses = st.multiselect("Status", status_values)
        filtered = discovery
        if search:
            needle = search.casefold()
            filtered = filtered[
                filtered[["source_project_id", "registry_name", "developer_name"]]
                .fillna("")
                .apply(lambda row: needle in " ".join(row.astype(str)).casefold(), axis=1)
            ]
        if statuses:
            filtered = filtered[filtered["project_status"].isin(statuses)]
        st.dataframe(
            filtered[["source_project_id", "registry_name", "developer_name", "project_status", "currently_tracked"]],
            hide_index=True,
            width="stretch",
            column_config={
                "source_project_id": "TEDUH code",
                "registry_name": "Registry name",
                "developer_name": "Developer",
                "project_status": "Status",
                "currently_tracked": "Tracked",
            },
        )
        untracked = filtered[filtered["currently_tracked"] == "No"]
        if not untracked.empty:
            st.markdown("#### Add a discovery result")
            choices = untracked.set_index("source_project_id").to_dict("index")
            with st.form("add_discovered_project"):
                discovered_code = st.selectbox(
                    "Project",
                    list(choices),
                    format_func=lambda value: f"{choices[value]['registry_name']} · {value}",
                )
                discovered_name = st.text_input("Actual/display name (optional)")
                discovered_parent = st.text_input("Parent group (optional)")
                discovered_set = st.selectbox(
                    "Project set",
                    list(PROJECT_SETS),
                    format_func=lambda value: SET_LABELS[value],
                )
                discovered_by = st.text_input(
                    "Added by (name or initials)",
                    value=st.session_state.get("audit_actor", ""),
                    key="discovery_changed_by",
                    help="Required for the audit log. Initials are sufficient for this local prototype.",
                )
                add_discovered = st.form_submit_button("Add to shortlist")
            if add_discovered:
                if not discovered_by.strip():
                    st.error("Enter your name or initials so this addition can be recorded in the audit log.")
                else:
                    upsert_shortlist_project(
                        SETTINGS,
                        {
                            "source_project_id": discovered_code,
                            "region": discovery_region,
                            "display_name": discovered_name or choices[discovered_code]["registry_name"],
                            "parent_group": discovered_parent,
                            "project_set": discovered_set,
                            "priority": "medium",
                            "tracking_notes": "",
                            "active": "Yes",
                            "origin": "teduh_discovery",
                        },
                        changed_by=discovered_by,
                    )
                    st.session_state["audit_actor"] = discovered_by.strip()
                    st.session_state["app_notice"] = (
                        f"Added TEDUH project {discovered_code} to the shortlist."
                    )
                    st.rerun()
    else:
        st.info(f"Run Discovery when you want to review the current {discovery_region} project catalogue.")

with alerts_tab:
    st.subheader("Monitoring alerts")
    st.caption("Direct TEDUH risk statuses appear immediately. Change-based alerts become available after at least two dated observations.")
    if not alert_rows:
        st.info("No alerts are available yet. Refresh the shortlist to create an observation.")
    else:
        severity_order = {"critical": 0, "high": 1, "info": 2}
        alerts = pd.DataFrame(alert_rows)
        if "region" not in alerts.columns:
            alerts["region"] = DEFAULT_REGION
        alert_region = st.radio(
            "Region",
            ["All regions"] + list(REGION_CONFIGS),
            horizontal=True,
            key="alerts_region",
            format_func=region_label,
        )
        if alert_region != "All regions":
            alerts = alerts[alerts["region"] == alert_region]
        alerts["region"] = alerts["region"].map(region_label)
        alerts["_rank"] = alerts["severity"].map(severity_order).fillna(9)
        alerts = alerts.sort_values(["_rank", "display_name"]).drop(columns="_rank")
        st.dataframe(
            alerts,
            hide_index=True,
            width="stretch",
            column_config={
                "snapshot_date": "Observation",
                "region": "Region",
                "severity": "Severity",
                "alert_code": "Alert",
                "source_project_id": "TEDUH code",
                "display_name": "Project",
                "message": "Explanation",
            },
        )

with audit_tab:
    st.subheader("Project audit log")
    st.caption(
        "Records project additions and field-by-field manual edits from this version onward. "
        "TEDUH data refreshes do not create manual-change entries."
    )
    if not audit_rows:
        st.info("No audited changes have been recorded yet. Earlier project history has not been reconstructed.")
    else:
        audit = pd.DataFrame(audit_rows)
        audit = audit.sort_values("event_timestamp", ascending=False)
        audit_search = st.text_input(
            "Search project, TEDUH code or person",
            key="audit_search",
        )
        audit_actions = st.multiselect(
            "Action",
            sorted(audit["action"].dropna().unique()),
            key="audit_actions",
        )
        if audit_search:
            needle = audit_search.casefold()
            audit = audit[
                audit[["project_name", "source_project_id", "changed_by"]]
                .fillna("")
                .apply(lambda row: needle in " ".join(row.astype(str)).casefold(), axis=1)
            ]
        if audit_actions:
            audit = audit[audit["action"].isin(audit_actions)]
        audit["event_timestamp"] = audit["event_timestamp"].map(display_timestamp)
        audit["project_name"] = audit.apply(
            lambda row: (
                row["project_name"]
                if row["project_name"] and row["project_name"] != row["source_project_id"]
                else (
                    shortlist_by_project.get(row["source_project_id"], {}).get("display_name")
                    or registry_name_by_code.get(row["source_project_id"])
                    or row["source_project_id"]
                )
            ),
            axis=1,
        )
        for field in ("field", "previous_value", "new_value"):
            audit[field] = audit[field].replace("", "—")
        st.dataframe(
            audit[
                [
                    "event_timestamp",
                    "changed_by",
                    "action",
                    "project_name",
                    "source_project_id",
                    "field",
                    "previous_value",
                    "new_value",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "event_timestamp": "When",
                "changed_by": "Changed by",
                "action": "Action",
                "project_name": "Project",
                "source_project_id": "TEDUH code",
                "field": "Field",
                "previous_value": "Previous value",
                "new_value": "New value",
            },
        )

st.markdown(
    '<div class="creator-footer">Concept and prototype by Lim Ri Jun</div>',
    unsafe_allow_html=True,
)
