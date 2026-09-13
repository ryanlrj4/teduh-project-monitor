from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from ..config import Settings
from ..monitor import snapshot_shortlist
from ..portfolios import MASTER_PORTFOLIO_ID, save_portfolio
from ..presentation import latest_project_changes, present_alert
from ..shortlist import PROJECT_SETS
from .components import render_project_details, render_refresh_status_panel
from .formatting import (
    display_text,
    money,
    pct,
    region_label,
    signed_number,
    status_change,
    whole_number,
)


SET_LABELS = {
    "reporting_set": "Reporting Set",
    "comparator_set": "Comparator Set",
    "general": "General",
}


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    first_latitude = math.radians(lat1)
    second_latitude = math.radians(lat2)
    latitude_delta = math.radians(lat2 - lat1)
    longitude_delta = math.radians(lon2 - lon1)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _portfolio_table(view: pd.DataFrame, *, key: str):
    table = view.copy().reset_index(drop=True)
    table["Group / developer"] = table.apply(
        lambda row: row.get("parent_group") or row.get("developer_name") or "N/A",
        axis=1,
    )
    table["Region"] = table["region"].map(region_label)
    table["Sold"] = table["sold_units"].map(whole_number)
    table["Units"] = table["reported_total_units"].map(whole_number)
    table["Unit sales"] = table["sales_percentage"].map(pct)
    table["Value sold"] = table["value_sold_percentage"].map(pct)
    table["Construction"] = table["construction_percentage"].map(pct)
    table["Remaining value"] = table["remaining_listed_value"].map(money)
    event = st.dataframe(
        table[
            [
                "display_name",
                "Group / developer",
                "Region",
                "project_status",
                "Sold",
                "Units",
                "Unit sales",
                "Value sold",
                "Construction",
                "Remaining value",
            ]
        ],
        hide_index=True,
        width="stretch",
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        selection_default={"selection": {"rows": [0]}},
        column_config={
            "display_name": "Project",
            "project_status": "TEDUH status",
        },
    )
    return table, event


def render_my_portfolio(
    current: pd.DataFrame,
    history: pd.DataFrame,
    alert_rows: list[dict[str, str]],
    *,
    portfolio_name: str,
    on_view_group=None,
) -> None:
    st.subheader("My Portfolio")
    st.caption(f"Active profile: {portfolio_name}. The home view prioritises its Reporting Set.")
    if current.empty:
        st.info("This profile has no projects. Add projects from Manage → Profiles.")
        return
    reporting = current[current["project_set"] == "reporting_set"].copy()
    if reporting.empty:
        st.info("This profile has no Reporting Set projects. Use Projects to review its other sets.")
        return

    source_codes = set(reporting["source_project_id"].astype(str))
    relevant_alerts = [
        present_alert(row)
        for row in alert_rows
        if str(row.get("source_project_id") or "") in source_codes
    ]
    risk_mask = reporting["project_status"].fillna("").str.casefold().str.contains(
        "sakit|lewat|batal"
    )
    changes = latest_project_changes(reporting, history)

    headline = st.columns(4)
    headline[0].metric("Reporting projects", f"{len(reporting):,}")
    headline[1].metric("Status exceptions", f"{int(risk_mask.sum()):,}")
    headline[2].metric("Projects changed", f"{len(changes):,}")
    headline[3].metric("Monitoring alerts", f"{len(relevant_alerts):,}")

    st.markdown("#### Needs attention")
    attention_rows: list[dict[str, str]] = []
    risk_project_codes = set(reporting.loc[risk_mask, "source_project_id"].astype(str))
    for _, row in reporting.loc[risk_mask].iterrows():
        attention_rows.append(
            {
                "Level": "Current exception",
                "Project": row.get("display_name") or row.get("project_name"),
                "Reason": f"TEDUH status: {display_text(row.get('project_status'))}",
            }
        )
    for row in relevant_alerts:
        if row.get("alert_level") not in {"Critical", "High", "Review"}:
            continue
        if (
            str(row.get("source_project_id") or "") in risk_project_codes
            and str(row.get("alert_code") or "")
            in {"status_sakit", "status_lewat", "permit_cancelled"}
        ):
            continue
        attention_rows.append(
            {
                "Level": str(row.get("alert_level")),
                "Project": str(row.get("display_name") or row.get("source_project_id")),
                "Reason": str(row.get("message") or row.get("alert_label")),
            }
        )
    if attention_rows:
        attention = pd.DataFrame(attention_rows).drop_duplicates()
        st.dataframe(attention, hide_index=True, width="stretch")
    else:
        st.success("No current Reporting Set exceptions or high-priority monitoring alerts.")

    with st.expander("Changes since the previous observation", expanded=not changes.empty):
        if changes.empty:
            st.info("No sales, construction or TEDUH status changes were recorded.")
        else:
            changes = changes.copy()
            changes["Units sold"] = changes["sold_units_delta"].map(
                lambda value: signed_number(value, zero_label="No change")
            )
            changes["Unit sales"] = changes["sales_percentage_delta"].map(
                lambda value: signed_number(value, decimals=1, suffix=" pp", zero_label="No change")
            )
            changes["Construction"] = changes["construction_percentage_delta"].map(
                lambda value: signed_number(value, decimals=1, suffix=" pp", zero_label="No change")
            )
            changes["Status"] = changes.apply(
                lambda row: status_change(row["previous_status"], row["current_status"]), axis=1
            )
            st.dataframe(
                changes[["display_name", "Status", "Units sold", "Unit sales", "Construction"]],
                hide_index=True,
                width="stretch",
                column_config={"display_name": "Project"},
            )

    st.markdown("#### Reporting Set")
    st.caption("Select a row to open the full monitoring view.")
    table, event = _portfolio_table(reporting.sort_values("display_name"), key="my_portfolio_table")
    if event.selection.rows:
        selected = table.iloc[event.selection.rows[0]]
        render_project_details(
            selected,
            history,
            container_key="my_portfolio_detail",
            manual_container_key="my_portfolio_manual",
            on_view_group=on_view_group,
        )


def render_groups(
    current: pd.DataFrame,
    history: pd.DataFrame,
    *,
    requested_group: str | None = None,
    on_view_group=None,
) -> None:
    st.subheader("Developer groups")
    st.caption("Review all tracked developments linked to the same locally maintained parent group.")
    if current.empty:
        st.info("No projects are available in this profile.")
        return
    groups = current.copy()
    groups["group_name"] = groups.apply(
        lambda row: row.get("parent_group") or row.get("developer_name") or "Unmapped",
        axis=1,
    )
    group_names = sorted(groups["group_name"].dropna().astype(str).unique(), key=str.casefold)
    initial = group_names.index(requested_group) if requested_group in group_names else 0
    selected_group = st.selectbox("Parent group / developer", group_names, index=initial)
    view = groups[groups["group_name"] == selected_group].copy()
    exceptions = view["project_status"].fillna("").str.casefold().str.contains("sakit|lewat|batal")
    total_units = pd.to_numeric(view["reported_total_units"], errors="coerce").sum(min_count=1)
    sold_units = pd.to_numeric(view["sold_units"], errors="coerce").sum(min_count=1)
    gdv = pd.to_numeric(view["potential_listed_gdv"], errors="coerce").sum(min_count=1)
    sold_value = pd.to_numeric(view["estimated_sold_value"], errors="coerce").sum(min_count=1)
    summary = st.columns(4)
    summary[0].metric("Tracked developments", f"{len(view):,}")
    summary[1].metric(
        "Portfolio unit sales",
        pct(sold_units / total_units * 100) if pd.notna(total_units) and total_units else "N/A",
    )
    summary[2].metric(
        "Portfolio value sold",
        pct(sold_value / gdv * 100) if pd.notna(gdv) and gdv else "N/A",
    )
    summary[3].metric("Status exceptions", f"{int(exceptions.sum()):,}")
    table, event = _portfolio_table(view.sort_values("display_name"), key="group_projects_table")
    if event.selection.rows:
        render_project_details(
            table.iloc[event.selection.rows[0]],
            history,
            container_key="group_project_detail",
            manual_container_key="group_project_manual",
            on_view_group=on_view_group,
        )


def render_compare(current: pd.DataFrame, history: pd.DataFrame, *, on_view_group=None) -> None:
    st.subheader("Compare projects")
    st.caption("Place Reporting, Comparator and General projects side by side using the same TEDUH-derived measures.")
    if current.empty:
        st.info("No projects are available in this profile.")
        return
    options = current.sort_values(["project_set", "display_name"]).copy()
    label_by_code = {
        str(row["source_project_id"]): (
            f"{row.get('display_name') or row.get('project_name')} · "
            f"{SET_LABELS.get(row.get('project_set'), row.get('project_set'))}"
        )
        for _, row in options.iterrows()
    }
    located = options.dropna(subset=["latitude", "longitude"]).copy()
    if len(located) > 1:
        with st.expander("Nearby comparator candidates"):
            anchor_code = st.selectbox(
                "Anchor project",
                list(located["source_project_id"].astype(str)),
                format_func=lambda code: label_by_code[code],
                key="comparison_anchor",
            )
            radius = st.slider("Distance radius (km)", 1, 30, 10)
            anchor = located[located["source_project_id"].astype(str) == anchor_code].iloc[0]
            candidates = located[
                located["source_project_id"].astype(str) != anchor_code
            ].copy()
            candidates["Distance"] = candidates.apply(
                lambda row: _distance_km(
                    float(anchor["latitude"]),
                    float(anchor["longitude"]),
                    float(row["latitude"]),
                    float(row["longitude"]),
                ),
                axis=1,
            )
            candidates = candidates[candidates["Distance"] <= radius].sort_values("Distance")
            if candidates.empty:
                st.info(f"No other profile projects have TEDUH coordinates within {radius} km.")
            else:
                candidates["Project"] = candidates["display_name"].fillna(candidates["project_name"])
                candidates["Set"] = candidates["project_set"].map(SET_LABELS)
                candidates["Distance"] = candidates["Distance"].map(lambda value: f"{value:.1f} km")
                candidates["Unit sales"] = candidates["sales_percentage"].map(pct)
                candidates["Construction"] = candidates["construction_percentage"].map(pct)
                st.dataframe(
                    candidates[["Project", "Set", "Distance", "Unit sales", "Construction"]].head(12),
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    "Distance uses TEDUH coordinates only. Geographic proximity is a starting point; the RM still decides whether a project is genuinely comparable."
                )
    reporting_codes = list(
        options.loc[options["project_set"] == "reporting_set", "source_project_id"].astype(str)
    )
    default_codes = reporting_codes[:1]
    comparator_codes = list(
        options.loc[options["project_set"] == "comparator_set", "source_project_id"].astype(str)
    )
    default_codes.extend(comparator_codes[: max(0, 3 - len(default_codes))])
    selected_codes = st.multiselect(
        "Projects (up to 6)",
        list(label_by_code),
        default=default_codes,
        format_func=lambda code: label_by_code[code],
        max_selections=6,
    )
    if not selected_codes:
        st.info("Choose at least one project to compare.")
        return
    selected = options[options["source_project_id"].astype(str).isin(selected_codes)].copy()
    selected["Project"] = selected["display_name"].fillna(selected["project_name"])
    selected["Set"] = selected["project_set"].map(SET_LABELS)
    selected["Unit sales"] = selected["sales_percentage"].map(pct)
    selected["Value sold"] = selected["value_sold_percentage"].map(pct)
    selected["Construction"] = selected["construction_percentage"].map(pct)
    selected["Sales vs construction"] = selected["sales_construction_gap"].map(
        lambda value: signed_number(value, decimals=1, suffix=" pp")
    )
    selected["Potential GDV"] = selected["potential_listed_gdv"].map(money)
    selected["Remaining value"] = selected["remaining_listed_value"].map(money)
    selected["Bumi sales"] = selected["bumi_sales_percentage"].map(pct)
    st.dataframe(
        selected[
            [
                "Project",
                "Set",
                "project_status",
                "Unit sales",
                "Value sold",
                "Construction",
                "Sales vs construction",
                "Potential GDV",
                "Remaining value",
                "Bumi sales",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={"project_status": "TEDUH status"},
    )
    detail_code = st.selectbox(
        "Open full details",
        selected_codes,
        format_func=lambda code: label_by_code[code],
    )
    detail = selected[selected["source_project_id"].astype(str) == detail_code].iloc[0]
    render_project_details(
        detail,
        history,
        container_key="compare_project_detail",
        manual_container_key="compare_project_manual",
        on_view_group=on_view_group,
    )


def render_profiles(
    settings: Settings,
    portfolios: list[dict[str, str]],
    memberships: list[dict[str, str]],
    shortlist_rows: list[dict[str, str]],
    registry_name_by_code: dict[str, str],
) -> None:
    st.subheader("Portfolio profiles")
    st.caption(
        "Profiles are saved project views, not access-control roles. TEDUH observations are stored once and reused across profiles."
    )
    profile_frame = pd.DataFrame(portfolios)
    st.dataframe(
        profile_frame[["portfolio_name", "description", "active"]],
        hide_index=True,
        width="stretch",
        column_config={
            "portfolio_name": "Profile",
            "description": "Purpose",
            "active": "Active",
        },
    )
    editable = [row for row in portfolios if row["portfolio_id"] != MASTER_PORTFOLIO_ID]
    mode_options = ["Create new"] + [row["portfolio_name"] for row in editable]
    mode = st.selectbox("Create or edit", mode_options)
    existing = next((row for row in editable if row["portfolio_name"] == mode), None)
    existing_id = existing["portfolio_id"] if existing else None
    existing_sets = {
        row["source_project_id"]: row["project_set"]
        for row in memberships
        if row["portfolio_id"] == existing_id
    }
    label_by_code = {
        row["source_project_id"]: (
            row.get("display_name")
            or registry_name_by_code.get(row["source_project_id"])
            or row["source_project_id"]
        )
        for row in shortlist_rows
    }
    name = st.text_input("Profile name", value=(existing or {}).get("portfolio_name", ""))
    description = st.text_input("Purpose", value=(existing or {}).get("description", ""))
    selected_codes = st.multiselect(
        "Projects",
        list(label_by_code),
        default=list(existing_sets),
        format_func=lambda code: f"{label_by_code[code]} · {code}",
    )
    assignments = pd.DataFrame(
        [
            {
                "TEDUH code": code,
                "Project": label_by_code[code],
                "Project set": existing_sets.get(code, "general"),
            }
            for code in selected_codes
        ]
    )
    if not assignments.empty:
        assignments = st.data_editor(
            assignments,
            hide_index=True,
            width="stretch",
            disabled=["TEDUH code", "Project"],
            column_config={
                "Project set": st.column_config.SelectboxColumn(
                    options=list(PROJECT_SETS),
                    required=True,
                )
            },
            key=f"profile_assignments_{existing_id or 'new'}",
        )
    if st.button("Save profile", type="primary"):
        if not name.strip():
            st.error("Enter a profile name.")
        elif assignments.empty:
            st.error("Select at least one project.")
        else:
            try:
                saved_id = save_portfolio(
                    settings,
                    portfolio_id=existing_id,
                    name=name,
                    description=description,
                    project_sets={
                        str(row["TEDUH code"]): str(row["Project set"])
                        for _, row in assignments.iterrows()
                    },
                )
                st.session_state["selected_portfolio"] = saved_id
                st.session_state["app_notice"] = f"Saved portfolio profile {name}."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def render_refresh_and_data_quality(settings: Settings) -> None:
    st.subheader("Refresh & data quality")
    st.caption(
        "Refreshes all active tracked projects once, validates the complete result, and preserves the previous valid snapshot if publication fails."
    )
    render_refresh_status_panel(settings)
    if not st.button("Refresh TEDUH projects", type="primary"):
        return
    progress_messages: list[str] = []
    refresh_progress = st.progress(0.0, text="Preparing TEDUH refresh…")

    def update_refresh_progress(
        completed: int,
        total: int,
        project_code: str,
        succeeded: bool,
    ) -> None:
        refresh_progress.progress(
            completed / total if total else 0.0,
            text=f"Reviewed {completed}/{total} projects · {project_code}",
        )

    try:
        with st.spinner("Refreshing active projects sequentially from TEDUH…"):
            result = snapshot_shortlist(
                settings,
                progress=progress_messages.append,
                project_progress=update_refresh_progress,
            )
        refresh_progress.progress(1.0, text="Refresh completed and validated")
        st.session_state["app_notice"] = (
            f"Refresh completed: {result['project_count']} projects and {result['alert_count']} alerts."
        )
        st.rerun()
    except Exception as exc:
        st.session_state["app_error"] = str(exc)
        st.rerun()
