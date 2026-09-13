from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import streamlit as st

from ..config import Settings
from ..refresh_status import load_refresh_history, load_refresh_status
from .formatting import (
    display_date,
    display_duration,
    display_text,
    display_timestamp,
    json_rows,
    money,
    numeric_range,
    pct,
    region_label,
    signed_number,
    source_money,
    status_help,
    status_change,
    whole_number,
)


def render_project_map(selected: pd.Series) -> None:
    try:
        latitude = float(selected.get("latitude"))
        longitude = float(selected.get("longitude"))
    except (TypeError, ValueError):
        latitude = longitude = float("nan")

    if pd.isna(latitude) or pd.isna(longitude) or not (-90 <= latitude <= 90) or not (
        -180 <= longitude <= 180
    ):
        st.markdown("**Coordinates · TEDUH**")
        st.write("N/A")
        return

    st.markdown("**Project marker · TEDUH**")
    st.caption(f"Coordinates · TEDUH: {latitude:.6f}, {longitude:.6f}")
    st.map(
        pd.DataFrame([{"latitude": latitude, "longitude": longitude}]),
        latitude="latitude",
        longitude="longitude",
        zoom=15,
        height=280,
    )


def render_refresh_status_panel(settings: Settings) -> None:
    status = load_refresh_status(settings)
    history_rows = load_refresh_history(settings)
    st.markdown("#### Refresh status")
    if not status:
        st.info("No refresh run has been recorded by this version yet.")
        return

    state = str(status.get("status") or "unknown")
    completed = int(status.get("completed_projects") or 0)
    total = int(status.get("total_projects") or 0)
    if state == "running":
        st.info(f"Refresh in progress: reviewed {completed}/{total} projects.")
        st.progress(completed / total if total else 0.0, text="TEDUH refresh in progress")
    elif state == "success":
        st.success("Last refresh completed validation and was published.")
    elif state == "failed":
        st.error("Last refresh failed validation. The previous valid snapshot remains in use.")
    else:
        st.warning(f"Refresh status: {state}")

    summary = st.columns(4)
    summary[0].metric("Last run", state.title())
    summary[1].metric(
        "Projects reviewed",
        f"{completed:,} / {total:,}",
    )
    summary[2].metric(
        "Duration",
        display_duration(status.get("duration_seconds")),
    )
    summary[3].metric(
        "TEDUH data through",
        display_date(
            status.get("source_dataset_as_of")
            or status.get("last_successful_source_dataset_as_of")
        ),
    )
    st.caption(
        f"Started {display_timestamp(status.get('started_at'))} · "
        f"Completed {display_timestamp(status.get('completed_at'))} · "
        f"Trigger: {display_text(status.get('trigger')).title()} · "
        f"Publication: {display_text(status.get('publication_status'))}"
    )
    if status.get("cached_projects") is not None:
        st.caption(
            f"Source requests: {int(status.get('cached_projects') or 0):,} projects reused the same-day cache; "
            f"{int(status.get('live_projects') or 0):,} required at least one live TEDUH request."
        )
    if status.get("error"):
        with st.expander("Failure details"):
            st.code(str(status["error"]), language=None)
    if history_rows:
        with st.expander("Recent refresh runs"):
            recent = pd.DataFrame(history_rows)
            recent["Run"] = recent["completed_at"].map(display_timestamp)
            recent["Status"] = recent["status"].astype(str).str.title()
            recent["Trigger"] = recent["trigger"].astype(str).str.title()
            recent["Projects"] = recent.apply(
                lambda row: f"{int(row.get('completed_projects') or 0):,} / {int(row.get('total_projects') or 0):,}",
                axis=1,
            )
            recent["Duration"] = recent["duration_seconds"].map(display_duration)
            st.dataframe(
                recent[["Run", "Status", "Trigger", "Projects", "Duration", "publication_status"]],
                hide_index=True,
                width="stretch",
                column_config={"publication_status": "Publication"},
            )


def render_weekly_progress(project_history: pd.DataFrame) -> None:
    st.markdown("#### Weekly progress")
    if project_history.empty:
        st.info("No dated observations have been stored for this project yet.")
        return
    weekly = project_history.copy()
    weekly["week_start"] = weekly["observation_date"] - pd.to_timedelta(
        weekly["observation_date"].dt.weekday, unit="D"
    )
    weekly = weekly.groupby("week_start", as_index=False).tail(1).sort_values("week_start")
    weekly["Week"] = weekly["week_start"].dt.strftime("%d %b %Y")
    weekly["Units sold"] = weekly["sold_units"]
    weekly["Weekly units sold"] = weekly["sold_units"].diff()
    weekly["Unit sales %"] = weekly["sales_percentage"]
    weekly["Unit sales change"] = weekly["sales_percentage"].diff()
    weekly["Value sold %"] = weekly.get("value_sold_percentage")
    weekly["Construction %"] = weekly["construction_percentage"]
    weekly["Construction change"] = weekly["construction_percentage"].diff()
    weekly["Status"] = weekly["project_status"].map(display_text)
    if len(weekly) == 1:
        st.info("Opening observation; changes begin with the next refresh.")
    chart_columns = ["Unit sales %", "Value sold %", "Construction %"]
    chart = weekly.set_index("week_start")[[
        column for column in chart_columns if column in weekly.columns
    ]].dropna(axis=1, how="all")
    if not chart.empty:
        st.line_chart(chart, height=250)
    weekly["Units sold display"] = weekly["Units sold"].map(whole_number)
    weekly["Weekly units sold display"] = weekly["Weekly units sold"].map(signed_number)
    weekly["Unit sales display"] = weekly["Unit sales %"].map(pct)
    weekly["Value sold display"] = weekly["Value sold %"].map(pct)
    weekly["Construction display"] = weekly["Construction %"].map(pct)
    st.dataframe(
        weekly[
            [
                "Week",
                "Units sold display",
                "Weekly units sold display",
                "Unit sales display",
                "Value sold display",
                "Construction display",
                "Status",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Units sold display": "Units sold",
            "Weekly units sold display": "Weekly units sold",
            "Unit sales display": "Unit sales",
            "Value sold display": "Value sold",
            "Construction display": "Construction",
        },
    )



def render_project_details(
    selected: pd.Series,
    observation_history: pd.DataFrame,
    *,
    container_key: str,
    manual_container_key: str,
    on_view_group: Callable[[str], None] | None = None,
) -> None:
    preferred_name = str(
        selected.get("display_name")
        or selected.get("project_name")
        or selected.get("source_project_id")
    )
    teduh_name = str(selected.get("project_name") or "")
    st.markdown(f"### {preferred_name}")
    if teduh_name and teduh_name.casefold() != preferred_name.casefold():
        st.caption(f"TEDUH registered name: {teduh_name}")

    project_history = (
        observation_history[
            observation_history["source_project_id"].astype(str)
            == str(selected.get("source_project_id"))
        ].copy()
        if not observation_history.empty
        else pd.DataFrame()
    )
    if not project_history.empty:
        project_history["observation_date"] = pd.to_datetime(
            project_history["snapshot_date"], errors="coerce"
        )
        project_history = project_history.dropna(subset=["observation_date"]).sort_values(
            ["observation_date", "retrieved_at"]
        )

    with st.container(border=True, key=container_key):
        identity_region, identity_left, identity_middle, identity_right, identity_status = st.columns(5)
        identity_region.markdown("**Region** · `TEDUH/local`")
        identity_region.write(region_label(selected.get("region")))
        identity_left.markdown("**Parent group** · `Local`")
        identity_left.write(display_text(selected.get("parent_group")))
        identity_middle.markdown("**Registered developer / SPV** · `TEDUH`")
        identity_middle.write(display_text(selected.get("developer_name")))
        identity_right.markdown("**Project code** · `TEDUH`")
        identity_right.write(display_text(selected.get("source_project_id")))
        identity_status.markdown(
            "**Current status** · `TEDUH`",
            help=status_help(selected.get("project_status")),
        )
        identity_status.write(display_text(selected.get("project_status")))
        parent_group = str(selected.get("parent_group") or "").strip()
        if parent_group and on_view_group is not None:
            st.button(
                f"View all {parent_group} developments",
                key=f"view_group_{container_key}_{selected.get('source_project_id')}",
                on_click=on_view_group,
                args=(parent_group,),
            )

        status_folded = str(selected.get("project_status") or "").casefold()
        if any(term in status_folded for term in ("sakit", "lewat", "batal")):
            st.error(f"TEDUH exception: {display_text(selected.get('project_status'))}")

        st.markdown("#### Current monitoring summary")
        progress_columns = st.columns(4)
        progress_columns[0].metric(
            "Units sold · Calculated",
            f"{whole_number(selected.get('sold_units'))} / {whole_number(selected.get('reported_total_units'))}",
            help="TEDUH unit records classified as sold.",
        )
        progress_columns[1].metric(
            "Unit sales · Calculated",
            pct(selected.get("sales_percentage")),
            help="Sold units / comparable unit records.",
        )
        progress_columns[2].metric(
            "Value sold · Calculated",
            pct(selected.get("value_sold_percentage")),
            help="Estimated sold value / potential listed GDV.",
        )
        progress_columns[3].metric(
            "Construction · Calculated",
            pct(selected.get("construction_percentage")),
            help="Unit-weighted TEDUH component progress.",
        )
        gap = selected.get("sales_construction_gap")
        if pd.notna(gap):
            st.caption(
                f"Sales vs construction: {signed_number(gap, decimals=1, suffix=' pp')}"
            )

        if len(project_history) >= 2:
            previous = project_history.iloc[-2]
            current_observation = project_history.iloc[-1]
            st.info(
                "Latest recorded movement: "
                f"units sold {signed_number(float(current_observation.get('sold_units') or 0) - float(previous.get('sold_units') or 0))}; "
                f"sales {signed_number(float(current_observation.get('sales_percentage') or 0) - float(previous.get('sales_percentage') or 0), decimals=1, suffix=' pp')}; "
                f"construction {signed_number(float(current_observation.get('construction_percentage') or 0) - float(previous.get('construction_percentage') or 0), decimals=1, suffix=' pp')}; "
                f"status {status_change(previous.get('project_status'), current_observation.get('project_status'))}."
            )

        value_columns = st.columns(4)
        value_columns[0].metric(
            "Potential listed GDV · Calculated",
            money(selected.get("potential_listed_gdv")),
            help="Sum of valid TEDUH listed unit prices.",
        )
        value_columns[1].metric(
            "Estimated value sold · Calculated",
            money(selected.get("estimated_sold_value")),
            help="Recorded SPA prices with listed-price fallback.",
        )
        value_columns[2].metric(
            "Recorded SPA value · Calculated",
            money(selected.get("recorded_spa_sales_value")),
            help="Available recorded SPA prices for sold units.",
        )
        value_columns[3].metric(
            "Remaining listed value · Calculated",
            money(selected.get("remaining_listed_value")),
            help="Listed prices for units not reported sold.",
        )

        price_columns = st.columns(4)
        price_columns[0].metric(
            "Typical listed unit price · Calculated",
            money(selected.get("median_listed_price_per_unit")),
            help="Median valid TEDUH listed unit price.",
        )
        price_columns[1].metric(
            "Average listed unit price · Calculated",
            money(selected.get("average_listed_price_per_unit")),
        )
        price_columns[2].metric(
            "Typical recorded SPA · Calculated",
            money(selected.get("median_recorded_spa_price_per_unit")),
            help="Median available recorded SPA price for sold units.",
        )
        price_columns[3].metric(
            "Average recorded SPA · Calculated",
            money(selected.get("average_recorded_spa_price_per_unit")),
            help=f"SPA price coverage: {pct(selected.get('spa_price_coverage_percentage'))}",
        )
        if pd.notna(selected.get("listed_price_p25")) and pd.notna(
            selected.get("listed_price_p75")
        ):
            st.caption(
                "Typical listed range: "
                + numeric_range(
                    selected.get("listed_price_p25"),
                    selected.get("listed_price_p75"),
                    prefix="RM ",
                )
            )

        render_weekly_progress(project_history)

        inventory_rows = json_rows(selected.get("remaining_inventory_json"))
        with st.expander("Remaining inventory, quota and recorded pricing"):
            inventory_summary = st.columns(4)
            inventory_summary[0].metric(
                "Remaining units · Calculated",
                whole_number(
                    float(selected.get("comparable_total_units") or 0)
                    - float(selected.get("sold_units") or 0)
                ),
            )
            inventory_summary[1].metric(
                "Bumiputera units sold",
                f"{whole_number(selected.get('bumi_sold_units'))} / {whole_number(selected.get('bumi_total_units'))}",
            )
            inventory_summary[2].metric(
                "Bumiputera unit sales",
                pct(selected.get("bumi_sales_percentage")),
            )
            inventory_summary[3].metric(
                "Recorded price realisation",
                pct(selected.get("recorded_price_realisation_percentage")),
                help="Recorded SPA value divided by listed value for sold units where both TEDUH prices are available.",
            )
            discount = selected.get("median_recorded_discount_percentage")
            if pd.notna(discount):
                st.caption(f"Median recorded discount to listed price: {pct(discount)}")
            if not inventory_rows:
                st.info("Inventory detail will appear after the next TEDUH refresh using v1.5.")
            else:
                inventory = pd.DataFrame(inventory_rows)
                inventory["Property type"] = inventory["property_type"].map(display_text)
                inventory["Quota"] = inventory["quota_category"].map(display_text)
                inventory["Units"] = inventory["units"].map(whole_number)
                inventory["Listed value"] = inventory["listed_value"].map(money)
                inventory["Price range"] = inventory.apply(
                    lambda row: numeric_range(
                        row.get("minimum_listed_price"),
                        row.get("maximum_listed_price"),
                        prefix="RM ",
                    ),
                    axis=1,
                )
                st.dataframe(
                    inventory[["Property type", "Quota", "Units", "Listed value", "Price range"]],
                    hide_index=True,
                    width="stretch",
                )

        component_sales = json_rows(selected.get("component_sales_json"))
        component_percentages = [
            float(row["sales_percentage"])
            for row in component_sales
            if row.get("sales_percentage") not in (None, "")
        ]
        component_dispersion = (
            max(component_percentages) - min(component_percentages)
            if len(component_percentages) > 1
            else 0
        )
        with st.expander(
            "Sales by TEDUH block/component",
            expanded=len(component_sales) > 1 and component_dispersion >= 10,
        ):
            if not component_sales:
                st.info("Component sales will appear after the next refresh using the updated data model.")
            else:
                component_frame = pd.DataFrame(component_sales)
                component_frame["Component"] = component_frame["component_label"].map(display_text)
                component_frame["Property type"] = component_frame["property_type"].map(display_text)
                component_frame["Sold"] = component_frame["sold_units"].map(whole_number)
                component_frame["Units"] = component_frame["total_units"].map(whole_number)
                component_frame["Sales"] = component_frame["sales_percentage"].map(pct)
                component_frame["Unsold"] = component_frame["unsold_units"].map(whole_number)
                component_frame["Confidence"] = component_frame["confidence"].astype(str).str.title()
                st.dataframe(
                    component_frame[
                        ["Component", "Property type", "Sold", "Units", "Sales", "Unsold", "Confidence"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
                if selected.get("component_sales_note") not in (None, "") and pd.notna(
                    selected.get("component_sales_note")
                ):
                    st.warning(str(selected.get("component_sales_note")))

        agreement_expanded = any(
            display_text(selected.get(field)) not in {"N/A", "Tidak", "No"}
            for field in ("vp_period_amended", "approved_extension_period", "revised_vp_date")
        )
        if agreement_expanded:
            st.warning("Contractual timeline amended or extended")
        with st.expander(
            "Contractual timeline and completion", expanded=agreement_expanded
        ):
            contract_top = st.columns(4)
            contract_top[0].metric(
                "Agreement type · TEDUH",
                display_text(selected.get("agreement_type")),
            )
            contract_top[1].metric(
                "Original construction period · TEDUH",
                display_text(selected.get("original_construction_period")),
            )
            contract_top[2].metric("First SPA · TEDUH", display_date(selected.get("first_spa_date")))
            contract_top[3].metric(
                "Original contractual VP · TEDUH", display_date(selected.get("expected_vp_date"))
            )
            contract_bottom = st.columns(4)
            contract_bottom[0].metric(
                "VP period amended · TEDUH", display_text(selected.get("vp_period_amended"))
            )
            contract_bottom[1].metric(
                "Approved extension · TEDUH", display_text(selected.get("approved_extension_period"))
            )
            contract_bottom[2].metric(
                "Revised construction period · TEDUH",
                display_text(selected.get("revised_construction_period")),
            )
            contract_bottom[3].metric(
                "Revised contractual VP · TEDUH", display_date(selected.get("revised_vp_date"))
            )
            completion = st.columns(3)
            completion[0].metric("CCC/CFO date · TEDUH", display_date(selected.get("ccc_date")))
            completion[1].metric("Actual VP date · TEDUH", display_date(selected.get("vp_date")))
            completion[2].metric(
                "SPA price range · TEDUH",
                numeric_range(
                    selected.get("teduh_spa_price_min"),
                    selected.get("teduh_spa_price_max"),
                    prefix="RM ",
                ),
            )

        construction_rows = json_rows(selected.get("construction_rows_json"))
        differing_component_statuses = len(
            {str(row.get("komponen") or "") for row in construction_rows}
        ) > 1
        with st.expander("Component construction details", expanded=differing_component_statuses):
            if not construction_rows:
                st.info("TEDUH component construction rows are unavailable for this project.")
            else:
                component_detail_rows = []
                for index, row in enumerate(construction_rows, start=1):
                    area = str(row.get("keluasan") or "").strip()
                    if area in {"", "0", "0.0", "-"}:
                        area = "N/A"
                    component_detail_rows.append(
                        {
                            "Component": f"Component {index}",
                            "Property type": display_text(row.get("jenis")),
                            "Floors": display_text(row.get("tingkat")),
                            "Bedrooms": display_text(row.get("bilik")),
                            "Bathrooms": display_text(row.get("tandas")),
                            "Built-up (m²)": area,
                            "Units": whole_number(row.get("unit")),
                            "Price range": f"{source_money(row.get('hargaMin'))}–{source_money(row.get('hargaMax')).replace('RM ', '')}",
                            "Construction": pct(float(row["peratus"]))
                            if row.get("peratus") not in (None, "", "-")
                            else "N/A",
                            "Status": display_text(row.get("komponen")),
                            "CCC/CFO": display_date(row.get("ccc")),
                            "VP": display_date(row.get("vp")),
                        }
                    )
                st.dataframe(component_detail_rows, hide_index=True, width="stretch")

        permit_history = json_rows(selected.get("permit_history_json"))
        with st.expander("Project, permit and developer details"):
            project_details = st.columns(4)
            project_details[0].metric(
                "Development · TEDUH", display_text(selected.get("development_type"))
            )
            project_details[1].metric("Location · TEDUH", display_text(selected.get("project_location")))
            project_details[2].metric("Current permit · TEDUH", display_text(selected.get("permit_number")))
            project_details[3].metric(
                "Permit validity · TEDUH",
                f"{display_date(selected.get('permit_start_date'))} – {display_date(selected.get('permit_end_date'))}",
            )
            developer_details = st.columns(4)
            developer_details[0].metric(
                "Developer status · TEDUH", display_text(selected.get("developer_status"))
            )
            developer_details[1].metric(
                "Developer code · TEDUH", display_text(selected.get("developer_id"))
            )
            developer_details[2].metric(
                "Developer licence · TEDUH", display_text(selected.get("developer_license_number"))
            )
            developer_details[3].metric(
                "Licence validity · TEDUH",
                f"{display_date(selected.get('developer_license_start_date'))} – {display_date(selected.get('developer_license_end_date'))}",
            )
            render_project_map(selected)
            if permit_history:
                st.markdown("**Previous advertising and sales permits · TEDUH**")
                history_display = [
                    {
                        "Permit": display_text(row.get("no_lesenpermit")),
                        "Start": display_date(row.get("tarikh_mula")),
                        "End": display_date(row.get("tarikh_luput")),
                        "Period": display_text(row.get("tempoh")),
                    }
                    for row in permit_history
                ]
                st.dataframe(history_display, hide_index=True, width="stretch")

        has_manual_launch = bool(str(selected.get("manual_launch_date") or "").strip())
        has_manual_built_up = pd.notna(selected.get("manual_built_up_min_sqft")) and pd.notna(
            selected.get("manual_built_up_max_sqft")
        )
        has_manual_psf = pd.notna(selected.get("manual_psf_min")) and pd.notna(
            selected.get("manual_psf_max")
        )
        has_manual_notes = bool(str(selected.get("tracking_notes") or "").strip())
        if has_manual_launch or has_manual_built_up or has_manual_psf or has_manual_notes:
            with st.expander("Locally entered supplementary details"):
                with st.container(key=manual_container_key):
                    manual_count = int(has_manual_launch) + int(has_manual_built_up) + int(has_manual_psf)
                    manual_columns = st.columns(manual_count) if manual_count else []
                    manual_index = 0
                    if has_manual_launch:
                        manual_columns[manual_index].metric(
                            "Launch date · Local", display_date(selected.get("manual_launch_date"))
                        )
                        manual_index += 1
                    if has_manual_built_up:
                        manual_columns[manual_index].metric(
                            "Built-up range · Local",
                            numeric_range(
                                selected.get("manual_built_up_min_sqft"),
                                selected.get("manual_built_up_max_sqft"),
                                suffix=" sqft",
                            ),
                        )
                        manual_index += 1
                    if has_manual_psf:
                        manual_columns[manual_index].metric(
                            "PSF range · Local",
                            numeric_range(
                                selected.get("manual_psf_min"),
                                selected.get("manual_psf_max"),
                                prefix="RM ",
                                suffix="/sqft",
                            ),
                        )
                    if has_manual_notes:
                        st.markdown("**Monitoring notes · Local**")
                        st.write(str(selected.get("tracking_notes")))

        with st.expander("Data provenance"):
            timing = st.columns(2)
            timing[0].metric(
                "Retrieved from TEDUH · Application",
                display_timestamp(selected.get("retrieved_at")),
            )
            timing[1].metric(
                "TEDUH displayed data through · TEDUH frontend",
                display_date(selected.get("source_dataset_as_of")),
            )
