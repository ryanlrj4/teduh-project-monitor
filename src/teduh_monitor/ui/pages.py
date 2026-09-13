from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..config import DEFAULT_REGION, REGION_CONFIGS, Settings
from ..discovery import discovery_manifest_path, load_discovery_catalog, run_discovery
from ..presentation import present_alert
from ..shortlist import PROJECT_SETS, upsert_shortlist_project
from .components import render_project_details
from .workspace_pages import render_refresh_and_data_quality
from .formatting import (
    display_date,
    display_text,
    display_timestamp,
    money,
    pct,
    region_label,
    whole_number,
)


SET_LABELS = {
    "reporting_set": "Reporting Set",
    "comparator_set": "Comparator Set",
    "general": "General",
}


def render_all_projects(
    current: pd.DataFrame,
    history: pd.DataFrame,
    *,
    on_view_group=None,
) -> None:
    st.subheader("All tracked projects")
    st.caption("Search and filter the complete Reporting Set, Comparator Set and General project universe.")
    if current.empty:
        st.info("Refresh the shortlist to populate current TEDUH metrics.")
    else:
        project_search, group_search = st.columns(2)
        project_query = project_search.text_input(
            "Search project name",
            key="all_projects_name_search",
            placeholder="Local or TEDUH registered name",
        )
        group_query = group_search.text_input(
            "Search parent group or developer",
            key="all_projects_group_search",
            placeholder="Parent group, developer or SPV",
        )

        filter_region, filter_set, filter_status = st.columns(3)
        region_filter = filter_region.selectbox(
            "Region",
            ["All regions"] + [
                region for region in REGION_CONFIGS if region in set(current["region"].dropna())
            ],
            format_func=region_label,
            key="all_projects_region",
        )
        available_sets = [value for value in PROJECT_SETS if value in set(current["project_set"].dropna())]
        set_filter = filter_set.multiselect(
            "Project set",
            available_sets,
            format_func=lambda value: SET_LABELS[value],
            key="all_projects_set",
        )
        available_statuses = sorted(value for value in current["project_status"].dropna().unique() if value)
        status_filter = filter_status.multiselect(
            "TEDUH status",
            available_statuses,
            key="all_projects_status",
        )
        all_view = current.copy()
        if region_filter != "All regions":
            all_view = all_view[all_view["region"] == region_filter]
        if set_filter:
            all_view = all_view[all_view["project_set"].isin(set_filter)]
        if status_filter:
            all_view = all_view[all_view["project_status"].isin(status_filter)]
        if project_query.strip():
            needle = project_query.strip().casefold()
            all_view = all_view[
                all_view[["display_name", "project_name"]]
                .fillna("")
                .apply(lambda row: needle in " ".join(row.astype(str)).casefold(), axis=1)
            ]
        if group_query.strip():
            needle = group_query.strip().casefold()
            all_view = all_view[
                all_view[["parent_group", "developer_name"]]
                .fillna("")
                .apply(lambda row: needle in " ".join(row.astype(str)).casefold(), axis=1)
            ]

        st.caption(f"Showing {len(all_view):,} of {len(current):,} projects")
        if all_view.empty:
            st.info("No projects match the selected filters.")
        else:
            all_view = all_view.copy()
            all_view["developer_or_parent_group"] = all_view.apply(
                lambda row: row.get("parent_group") or row.get("developer_name") or "N/A",
                axis=1,
            )
            all_view["region_display"] = all_view["region"].map(region_label)
            all_view["project_set_display"] = (
                all_view["project_set"].map(SET_LABELS).fillna(all_view["project_set"])
            )
            all_view["sold_display"] = all_view["sold_units"].map(whole_number)
            all_view["units_display"] = all_view["reported_total_units"].map(whole_number)
            all_view["sales_display"] = all_view["sales_percentage"].map(pct)
            all_view["construction_display"] = all_view["construction_percentage"].map(pct)
            all_view["potential_gdv_display"] = all_view["potential_listed_gdv"].map(money)
            set_order = {"reporting_set": 0, "general": 1, "comparator_set": 2}
            all_view["_set_rank"] = all_view["project_set"].map(set_order).fillna(9)
            all_view = all_view.sort_values(["_set_rank", "display_name"]).reset_index(drop=True)
            all_projects_event = st.dataframe(
                all_view[
                    [
                        "display_name",
                        "developer_or_parent_group",
                        "region_display",
                        "project_status",
                        "sold_display",
                        "units_display",
                        "sales_display",
                        "construction_display",
                        "potential_gdv_display",
                        "project_set_display",
                    ]
                ],
                hide_index=True,
                width="stretch",
                key="all_projects_snapshot",
                on_select="rerun",
                selection_mode="single-row",
                selection_default={"selection": {"rows": [0]}},
                column_config={
                    "display_name": "Project",
                    "developer_or_parent_group": "Parent group / developer",
                    "region_display": "Region",
                    "project_status": "TEDUH status",
                    "sold_display": "Sold",
                    "units_display": "Units",
                    "sales_display": "Sales",
                    "construction_display": "Construction",
                    "potential_gdv_display": "Potential GDV",
                    "project_set_display": "Project set",
                },
            )
            selected_all_rows = all_projects_event.selection.rows
            if selected_all_rows:
                selected_all = all_view.iloc[selected_all_rows[0]]
                render_project_details(
                    selected_all,
                    history,
                    container_key="all_projects_detail_panel",
                    manual_container_key="all_projects_manual_project_details",
                    on_view_group=on_view_group,
                )



def render_shortlist(
    settings: Settings,
    shortlist_rows: list[dict[str, str]],
    registry_name_by_code: dict[str, str],
    *,
    include_refresh: bool = True,
) -> None:
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
                ["source_project_id", "region_display", "display_name", "parent_group", "project_set", "active", "tracking_notes"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "source_project_id": "TEDUH code",
                "region_display": "Region",
                "display_name": "Display name (local or TEDUH)",
                "parent_group": "Parent group",
                "project_set": "Project set",
                "active": "Active",
                "tracking_notes": "Your notes",
            },
        )
    if include_refresh:
        render_refresh_and_data_quality(settings)



def render_add_or_edit(
    settings: Settings,
    shortlist_rows: list[dict[str, str]],
    registry_name_by_code: dict[str, str],
) -> None:
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
        third, fourth = st.columns(2)
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
                    settings,
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



def render_discovery(
    settings: Settings,
    shortlist_rows: list[dict[str, str]],
) -> None:
    st.subheader("On-demand regional discovery")
    st.caption("Discovery can make at most one live catalogue request set per region each day. A second run reuses that region's same-day cache.")
    discovery_region = st.selectbox(
        "Region", list(REGION_CONFIGS), key="discovery_region", format_func=region_label
    )
    manifest_path = discovery_manifest_path(settings, discovery_region)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        st.info(f"Last discovery: {manifest.get('discovery_date')} · {manifest.get('project_count', 0):,} catalogue projects")
    if st.button("Run Discovery", type="primary"):
        messages: list[str] = []
        try:
            with st.spinner(f"Reviewing the {discovery_region} TEDUH catalogue…"):
                result = run_discovery(
                    settings,
                    region=discovery_region,
                    progress=messages.append,
                )
            action = "Live discovery completed" if result["live_request_performed"] else "Same-day discovery cache reused"
            st.session_state["app_notice"] = f"{action}: {result['project_count']:,} projects."
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    discovery_rows = load_discovery_catalog(settings, discovery_region)
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
                        settings,
                        {
                            "source_project_id": discovered_code,
                            "region": discovery_region,
                            "display_name": discovered_name or choices[discovered_code]["registry_name"],
                            "parent_group": discovered_parent,
                            "project_set": discovered_set,
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



def render_alerts(
    alert_rows: list[dict[str, str]],
    shortlist_by_project: dict[str, dict[str, str]],
) -> None:
    st.subheader("Monitoring alerts")
    st.caption("Current TEDUH status exceptions appear immediately. Change-based alerts become available after at least two dated observations.")
    if not alert_rows:
        st.info("No alerts are available yet. Refresh the shortlist to create an observation.")
    else:
        alert_level_order = {"Critical": 0, "High": 1, "Review": 2, "Notice": 3}
        alerts = pd.DataFrame([present_alert(row) for row in alert_rows])
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
        alerts["project_set"] = alerts["source_project_id"].astype(str).map(
            lambda code: shortlist_by_project.get(code, {}).get("project_set") or "general"
        )
        alerts["region"] = alerts["region"].map(region_label)
        alerts["_rank"] = alerts["alert_level"].map(alert_level_order).fillna(9)
        alerts = alerts.sort_values(["_rank", "display_name"])
        alert_columns = [
            "snapshot_date",
            "region",
            "alert_level",
            "alert_category",
            "alert_label",
            "source_project_id",
            "display_name",
            "message",
        ]
        alert_column_config = {
            "snapshot_date": "Observation",
            "region": "Region",
            "alert_level": "Level",
            "alert_category": "Category",
            "alert_label": "Alert",
            "source_project_id": "TEDUH code",
            "display_name": "Project",
            "message": "Explanation",
        }
        for project_set in ("reporting_set", "comparator_set", "general"):
            set_alerts = alerts[alerts["project_set"] == project_set]
            st.markdown(f"#### {SET_LABELS[project_set]} alerts ({len(set_alerts):,})")
            if set_alerts.empty:
                st.info(f"No {SET_LABELS[project_set].lower()} alerts for the selected region.")
                continue
            st.dataframe(
                set_alerts[alert_columns],
                hide_index=True,
                width="stretch",
                column_config=alert_column_config,
            )



def render_audit_log(
    audit_rows: list[dict[str, str]],
    shortlist_by_project: dict[str, dict[str, str]],
    registry_name_by_code: dict[str, str],
) -> None:
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
