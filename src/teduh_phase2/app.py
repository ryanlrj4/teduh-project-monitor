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
from teduh_phase2.presentation import latest_project_changes, present_alert
from teduh_phase2.refresh_status import load_refresh_history, load_refresh_status
from teduh_phase2.shortlist import (
    PROJECT_SETS,
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
    [data-testid="stIconMaterial"], .material-symbols-rounded {
        font-family: "Material Symbols Rounded" !important;
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
    .st-key-project_detail_panel [data-testid="stMetric"],
    .st-key-all_projects_detail_panel [data-testid="stMetric"] {
        border-top-width: 2px;
        padding: 10px 12px;
        min-height: 0;
    }
    .st-key-project_detail_panel [data-testid="stMetricLabel"] p,
    .st-key-all_projects_detail_panel [data-testid="stMetricLabel"] p {
        font-size: .78rem !important;
        line-height: 1.2 !important;
    }
    .st-key-project_detail_panel [data-testid="stMetricValue"],
    .st-key-all_projects_detail_panel [data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        line-height: 1.3 !important;
    }
    .st-key-manual_project_details,
    .st-key-all_projects_manual_project_details {
        background: var(--ocbc-surface);
        border-left: 4px solid var(--ocbc-muted);
        border-radius: 5px;
        padding: .75rem 1rem .4rem;
        margin: .65rem 0 1rem;
    }
    .st-key-manual_project_details [data-testid="stMetric"],
    .st-key-all_projects_manual_project_details [data-testid="stMetric"] {
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
        return "N/A"
    return f"RM {float(value):,.0f}"


def source_money(value: object) -> str:
    if value in (None, "", "-"):
        return "N/A"
    try:
        return f"RM {float(str(value).replace(',', '').replace('RM', '').strip()):,.0f}"
    except ValueError:
        return "N/A"


def numeric_range(
    minimum: object,
    maximum: object,
    *,
    prefix: str = "",
    suffix: str = "",
    decimals: int = 0,
) -> str:
    if minimum in (None, "") or maximum in (None, "") or pd.isna(minimum) or pd.isna(maximum):
        return "N/A"
    low = float(minimum)
    high = float(maximum)
    formatter = f",.{decimals}f"
    if round(low, decimals) == round(high, decimals):
        return f"{prefix}{format(low, formatter)}{suffix}"
    return f"{prefix}{format(low, formatter)}–{format(high, formatter)}{suffix}"


def whole_number(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    return f"{int(float(value)):,}"


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"


def display_date(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    parsed = pd.to_datetime(value, errors="coerce")
    return "N/A" if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def display_timestamp(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.strftime("%d %b %Y, %I:%M %p")


def region_label(value: object) -> str:
    text = str(value or "N/A")
    return REGION_LABELS.get(text, text)


def signed_number(
    value: object,
    *,
    decimals: int = 0,
    suffix: str = "",
    zero_label: str | None = None,
) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if zero_label is not None and abs(number) < 1e-9:
        return zero_label
    return f"{number:+,.{decimals}f}{suffix}"


def status_change(previous: object, current_value: object) -> str:
    previous_text = str(previous or "N/A")
    current_text = str(current_value or "N/A")
    return "No change" if previous_text == current_text else f"{previous_text} → {current_text}"


def display_text(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return "N/A"
    return str(value)


def json_rows(value: object) -> list[dict[str, object]]:
    if value in (None, "") or pd.isna(value):
        return []
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def display_duration(value: object) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f} sec"
    minutes, remaining = divmod(int(round(seconds)), 60)
    return f"{minutes} min {remaining:02d} sec"


def render_refresh_status_panel() -> None:
    status = load_refresh_status(SETTINGS)
    history_rows = load_refresh_history(SETTINGS)
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
    summary[0].metric(
        "Last run",
        state.title(),
        help="Application-generated status for the most recent refresh attempt.",
    )
    summary[1].metric(
        "Projects reviewed",
        f"{completed:,} / {total:,}",
        help="Application-generated count of active shortlist projects reviewed in the run.",
    )
    summary[2].metric(
        "Duration",
        display_duration(status.get("duration_seconds")),
        help="Application-generated elapsed time for the refresh attempt.",
    )
    summary[3].metric(
        "TEDUH data through",
        display_date(
            status.get("source_dataset_as_of")
            or status.get("last_successful_source_dataset_as_of")
        ),
        help="TEDUH frontend data-through label; not a per-project API update timestamp.",
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
        "developer_project_count",
        "latitude",
        "longitude",
        "component_sales_count",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def render_project_details(
    selected: pd.Series,
    observation_history: pd.DataFrame,
    *,
    container_key: str,
    manual_container_key: str,
) -> None:
    """Render the complete project-detail hierarchy for any tracked project."""
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
        identity_status.markdown("**Current status** · `TEDUH`")
        identity_status.write(display_text(selected.get("project_status")))

        status_folded = str(selected.get("project_status") or "").casefold()
        if any(term in status_folded for term in ("sakit", "lewat", "batal")):
            st.error(
                f"Current TEDUH exception: {display_text(selected.get('project_status'))}. "
                "This is a public HIMS project classification, not a customer or facility risk classification."
            )

        st.markdown("#### Current monitoring summary")
        progress_columns = st.columns(5)
        progress_columns[0].metric(
            "Units sold · Calculated",
            f"{whole_number(selected.get('sold_units'))} / {whole_number(selected.get('reported_total_units'))}",
            help="Calculated from individual TEDUH unit sales statuses.",
        )
        progress_columns[1].metric(
            "Sales · Calculated",
            pct(selected.get("sales_percentage")),
            help="Sold units divided by comparable TEDUH unit records; not an official TEDUH percentage.",
        )
        progress_columns[2].metric(
            "Construction · Calculated",
            pct(selected.get("construction_percentage")),
            help="Unit-weighted calculation from TEDUH component rows where reconciliation checks pass.",
        )
        progress_columns[3].metric(
            "CCC/CFO · TEDUH",
            display_text(selected.get("ccc_obtained")),
            help="Based on TEDUH project or component completion evidence.",
        )
        progress_columns[4].metric(
            "Actual VP · TEDUH",
            display_date(selected.get("vp_date")),
            help="Latest valid VP date in TEDUH's component-status rows.",
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
            help="Sum of TEDUH listed unit prices when coverage and reconciliation checks pass.",
        )
        value_columns[1].metric(
            "Estimated value sold · Calculated",
            money(selected.get("estimated_sold_value")),
            help="Uses recorded SPA prices where available and TEDUH listed-price fallback otherwise.",
        )
        value_columns[2].metric(
            "Recorded SPA value · Calculated",
            money(selected.get("recorded_spa_sales_value")),
            help="Sum of available TEDUH SPA prices for sold unit records.",
        )
        value_columns[3].metric(
            "Remaining listed value · Calculated",
            money(selected.get("remaining_listed_value")),
            help="Sum of TEDUH listed prices for non-sold unit records where coverage checks pass.",
        )
        st.caption(
            "Value measures are analytical monitoring estimates, not audited developer GDV, revenue or credit conclusions."
        )

        component_sales = json_rows(selected.get("component_sales_json"))
        with st.expander("Sales by TEDUH block/component", expanded=len(component_sales) > 1):
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
                st.caption(
                    "Calculated independently from each TEDUH unit group. Neutral component labels are used when TEDUH supplies no block name; unit-number prefixes are not interpreted as block names."
                )
                if selected.get("component_sales_note") not in (None, "") and pd.notna(
                    selected.get("component_sales_note")
                ):
                    st.warning(str(selected.get("component_sales_note")))

        agreement_expanded = any(
            display_text(selected.get(field)) not in {"N/A", "Tidak", "No"}
            for field in ("vp_period_amended", "approved_extension_period", "revised_vp_date")
        )
        with st.expander("Contractual timeline and completion", expanded=agreement_expanded):
            contract_top = st.columns(4)
            contract_top[0].metric("Agreement type · TEDUH", display_text(selected.get("agreement_type")))
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
                st.caption(
                    "TEDUH component status is based on the latest HIMS 7(f) reporting. Component construction rows are not joined to sales groups unless TEDUH provides a reliable shared identifier."
                )

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
                    st.caption("These fields are maintained locally and do not come from TEDUH.")
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

        with st.expander("Weekly progress and data provenance"):
            timing = st.columns(2)
            timing[0].metric(
                "Retrieved from TEDUH · Application",
                display_timestamp(selected.get("retrieved_at")),
                help="Timestamp generated by this application when the API response was obtained.",
            )
            timing[1].metric(
                "TEDUH displayed data through · TEDUH frontend",
                display_date(selected.get("source_dataset_as_of")),
                help="Portal-wide TEDUH frontend label; not an authoritative per-project API timestamp.",
            )
            if project_history.empty:
                st.info("No dated observations have been stored for this project yet.")
            else:
                project_history["week_start"] = project_history["observation_date"] - pd.to_timedelta(
                    project_history["observation_date"].dt.weekday, unit="D"
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
                        "This is the opening observation. Past sales dates cannot be reconstructed from TEDUH's current snapshot."
                    )
                chart = weekly.set_index("week_start")[["Sales %", "Construction %"]].dropna(
                    axis=1, how="all"
                )
                if not chart.empty:
                    st.line_chart(chart, height=260)
                weekly["Units sold display"] = weekly["Units sold"].map(whole_number)
                weekly["Weekly units sold display"] = weekly["Weekly units sold"].map(signed_number)
                weekly["Sales display"] = weekly["Sales %"].map(pct)
                weekly["Sales change display"] = weekly["Sales change"].map(
                    lambda value: signed_number(value, decimals=1, suffix=" pp")
                )
                weekly["Construction display"] = weekly["Construction %"].map(pct)
                weekly["Construction change display"] = weekly["Construction change"].map(
                    lambda value: signed_number(value, decimals=1, suffix=" pp")
                )
                st.dataframe(
                    weekly[
                        [
                            "Week",
                            "Units sold display",
                            "Weekly units sold display",
                            "Sales display",
                            "Sales change display",
                            "Construction display",
                            "Construction change display",
                            "Status",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Units sold display": "Units sold",
                        "Weekly units sold display": "Weekly units sold",
                        "Sales display": "Sales",
                        "Sales change display": "Sales change",
                        "Construction display": "Construction",
                        "Construction change display": "Construction change",
                    },
                )


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
app_error = st.session_state.pop("app_error", None)
if app_error:
    st.error(app_error)

overview_tab, all_projects_tab, shortlist_tab, add_tab, discovery_tab, alerts_tab, audit_tab = st.tabs(
    ["Overview", "All projects", "Shortlist", "Add or edit", "Discovery", "Alerts", "Audit log"]
)

with overview_tab:
    if current.empty:
        st.info("The authorized starter shortlist is ready. Run the first shortlist refresh to populate TEDUH metrics.")
        st.caption(f"Tracking {len(active_shortlist):,} projects")
    else:
        reporting_current = current[current["project_set"] == "reporting_set"].copy()
        if reporting_current.empty:
            st.info("No Reporting Set projects are currently available. Add them from the Shortlist or Discovery tabs.")
            st.stop()
        observed_regions = set(reporting_current["region"].dropna().astype(str))
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
            reporting_current
            if selected_region == "All regions"
            else reporting_current[reporting_current["region"] == selected_region]
        )
        st.caption(f"Showing {len(view):,} Reporting Set projects")
        risk_mask = view["project_status"].fillna("").str.casefold().str.contains("sakit|lewat|batal")

        st.subheader("Changes since the previous observation")
        changes = latest_project_changes(view, history)
        if changes.empty:
            st.info("No sales, construction or TEDUH status changes were recorded for these projects.")
        else:
            changes["region_display"] = changes["region"].map(region_label)
            changes["status_display"] = changes.apply(
                lambda row: status_change(row["previous_status"], row["current_status"]), axis=1
            )
            changes["sold_change_display"] = changes["sold_units_delta"].map(
                lambda value: signed_number(value, zero_label="No change")
            )
            changes["sales_change_display"] = changes["sales_percentage_delta"].map(
                lambda value: signed_number(value, decimals=1, suffix=" pp", zero_label="No change")
            )
            changes["construction_change_display"] = changes["construction_percentage_delta"].map(
                lambda value: signed_number(value, decimals=1, suffix=" pp", zero_label="No change")
            )
            changes["comparison_display"] = changes.apply(
                lambda row: f"{display_date(row['previous_snapshot_date'])} → {display_date(row['current_snapshot_date'])}",
                axis=1,
            )
            change_columns = [
                "display_name",
                "region_display",
                "status_display",
                "sold_change_display",
                "sales_change_display",
                "construction_change_display",
                "comparison_display",
            ]
            st.dataframe(
                changes[change_columns],
                hide_index=True,
                width="stretch",
                column_config={
                    "display_name": "Project",
                    "region_display": "Region",
                    "status_display": "TEDUH status",
                    "sold_change_display": "Units sold",
                    "sales_change_display": "Sales",
                    "construction_change_display": "Construction",
                    "comparison_display": "Compared observations",
                },
            )
        st.caption("Each project is compared with its latest earlier dated observation.")

        st.subheader("Current TEDUH Exceptions")
        risk_columns = ["display_name", "parent_group", "project_status", "sales_percentage", "construction_percentage"]
        if selected_region == "All regions":
            risk_columns.insert(1, "region")
        risk = view.loc[
            risk_mask,
            risk_columns,
        ].copy()
        risk["parent_group"] = risk["parent_group"].fillna("").replace("", "N/A")
        if "region" in risk.columns:
            risk["region"] = risk["region"].map(region_label)
        if risk.empty:
            st.success("No current Sakit, Lewat or cancelled statuses.")
        else:
            risk["sales_display"] = risk["sales_percentage"].map(pct)
            risk["construction_display"] = risk["construction_percentage"].map(pct)
            risk = risk.drop(columns=["sales_percentage", "construction_percentage"])
            st.dataframe(
                risk,
                hide_index=True,
                width="stretch",
                column_config={
                    "display_name": "Project",
                    "region": "Region",
                    "parent_group": "Parent group",
                    "project_status": "Status",
                    "sales_display": "Sales",
                    "construction_display": "Construction",
                },
            )

        st.subheader("Current Reporting Set snapshot")
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
            registered_developer = str(selected.get("developer_name") or "N/A")

            st.markdown(f"### {preferred_name}")
            if teduh_name and teduh_name.casefold() != preferred_name.casefold():
                st.caption(f"TEDUH registered name: {teduh_name}")

            project_history = (
                history[
                    history["source_project_id"].astype(str)
                    == str(selected.get("source_project_id"))
                ].copy()
                if not history.empty
                else pd.DataFrame()
            )
            if not project_history.empty:
                project_history["observation_date"] = pd.to_datetime(
                    project_history["snapshot_date"], errors="coerce"
                )
                project_history = project_history.dropna(subset=["observation_date"]).sort_values(
                    ["observation_date", "retrieved_at"]
                )

            with st.container(border=True, key="project_detail_panel"):
                identity_region, identity_left, identity_middle, identity_right, identity_status = st.columns(5)
                identity_region.markdown("**Region** · `TEDUH/local`")
                identity_region.write(region_label(selected.get("region")))
                identity_left.markdown("**Parent group** · `Local`")
                identity_left.write(parent_group or "N/A")
                identity_middle.markdown("**Registered developer / SPV** · `TEDUH`")
                identity_middle.write(registered_developer)
                identity_right.markdown("**Project code** · `TEDUH`")
                identity_right.write(str(selected.get("source_project_id") or "N/A"))
                identity_status.markdown("**Current status** · `TEDUH`")
                identity_status.write(display_text(selected.get("project_status")))

                status_folded = str(selected.get("project_status") or "").casefold()
                if any(term in status_folded for term in ("sakit", "lewat", "batal")):
                    st.error(
                        f"Current TEDUH exception: {display_text(selected.get('project_status'))}. "
                        "This is a public HIMS project classification, not a customer or facility risk classification."
                    )

                st.markdown("#### Current monitoring summary")
                progress_columns = st.columns(5)
                progress_columns[0].metric(
                    "Units sold · Calculated",
                    f"{whole_number(selected.get('sold_units'))} / {whole_number(selected.get('reported_total_units'))}",
                    help="Calculated from individual TEDUH unit sales statuses.",
                )
                progress_columns[1].metric(
                    "Sales · Calculated",
                    pct(selected.get("sales_percentage")),
                    help="Sold units divided by comparable TEDUH unit records; not an official TEDUH percentage.",
                )
                progress_columns[2].metric(
                    "Construction · Calculated",
                    pct(selected.get("construction_percentage")),
                    help="Unit-weighted calculation from TEDUH component rows where reconciliation checks pass.",
                )
                progress_columns[3].metric(
                    "CCC/CFO · TEDUH",
                    display_text(selected.get("ccc_obtained")),
                    help="Based on TEDUH project or component completion evidence.",
                )
                progress_columns[4].metric(
                    "Actual VP · TEDUH",
                    display_date(selected.get("vp_date")),
                    help="Latest valid VP date in TEDUH's component-status rows.",
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
                    help="Sum of TEDUH listed unit prices when coverage and reconciliation checks pass.",
                )
                value_columns[1].metric(
                    "Estimated value sold · Calculated",
                    money(selected.get("estimated_sold_value")),
                    help="Uses recorded SPA prices where available and TEDUH listed-price fallback otherwise.",
                )
                value_columns[2].metric(
                    "Recorded SPA value · Calculated",
                    money(selected.get("recorded_spa_sales_value")),
                    help="Sum of available TEDUH SPA prices for sold unit records.",
                )
                value_columns[3].metric(
                    "Remaining listed value · Calculated",
                    money(selected.get("remaining_listed_value")),
                    help="Sum of TEDUH listed prices for non-sold unit records where coverage checks pass.",
                )
                st.caption(
                    "Value measures are analytical monitoring estimates, not audited developer GDV, revenue or credit conclusions."
                )

                component_sales = json_rows(selected.get("component_sales_json"))
                multiple_components = len(component_sales) > 1
                with st.expander(
                    "Sales by TEDUH block/component",
                    expanded=multiple_components,
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
                        st.caption(
                            "Calculated independently from each TEDUH unit group. Neutral component labels are used when TEDUH supplies no block name; unit-number prefixes are not interpreted as block names."
                        )
                        if selected.get("component_sales_note") not in (None, "") and pd.notna(
                            selected.get("component_sales_note")
                        ):
                            st.warning(str(selected.get("component_sales_note")))

                agreement_expanded = any(
                    display_text(selected.get(field)) not in {"N/A", "Tidak", "No"}
                    for field in ("vp_period_amended", "approved_extension_period", "revised_vp_date")
                )
                with st.expander("Contractual timeline and completion", expanded=agreement_expanded):
                    contract_top = st.columns(4)
                    contract_top[0].metric(
                        "Agreement type · TEDUH",
                        display_text(selected.get("agreement_type")),
                        help="Type of statutory sale and purchase agreement reported by TEDUH.",
                    )
                    contract_top[1].metric(
                        "Original construction period · TEDUH",
                        display_text(selected.get("original_construction_period")),
                    )
                    contract_top[2].metric(
                        "First SPA · TEDUH",
                        display_date(selected.get("first_spa_date")),
                    )
                    contract_top[3].metric(
                        "Original contractual VP · TEDUH",
                        display_date(selected.get("expected_vp_date")),
                    )
                    contract_bottom = st.columns(4)
                    contract_bottom[0].metric(
                        "VP period amended · TEDUH",
                        display_text(selected.get("vp_period_amended")),
                    )
                    contract_bottom[1].metric(
                        "Approved extension · TEDUH",
                        display_text(selected.get("approved_extension_period")),
                    )
                    contract_bottom[2].metric(
                        "Revised construction period · TEDUH",
                        display_text(selected.get("revised_construction_period")),
                    )
                    contract_bottom[3].metric(
                        "Revised contractual VP · TEDUH",
                        display_date(selected.get("revised_vp_date")),
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
                with st.expander(
                    "Component construction details",
                    expanded=differing_component_statuses,
                ):
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
                                    "Construction": pct(float(row["peratus"])) if row.get("peratus") not in (None, "", "-") else "N/A",
                                    "Status": display_text(row.get("komponen")),
                                    "CCC/CFO": display_date(row.get("ccc")),
                                    "VP": display_date(row.get("vp")),
                                }
                            )
                        st.dataframe(component_detail_rows, hide_index=True, width="stretch")
                        st.caption(
                            "TEDUH component status is based on the latest HIMS 7(f) reporting. Component construction rows are not joined to sales groups unless TEDUH provides a reliable shared identifier."
                        )

                permit_history = json_rows(selected.get("permit_history_json"))
                with st.expander("Project, permit and developer details"):
                    project_details = st.columns(4)
                    project_details[0].metric("Development · TEDUH", display_text(selected.get("development_type")))
                    project_details[1].metric("Location · TEDUH", display_text(selected.get("project_location")))
                    project_details[2].metric("Current permit · TEDUH", display_text(selected.get("permit_number")))
                    project_details[3].metric(
                        "Permit validity · TEDUH",
                        f"{display_date(selected.get('permit_start_date'))} – {display_date(selected.get('permit_end_date'))}",
                    )
                    developer_details = st.columns(4)
                    developer_details[0].metric("Developer status · TEDUH", display_text(selected.get("developer_status")))
                    developer_details[1].metric("Developer code · TEDUH", display_text(selected.get("developer_id")))
                    developer_details[2].metric(
                        "Developer licence · TEDUH", display_text(selected.get("developer_license_number"))
                    )
                    developer_details[3].metric(
                        "Licence validity · TEDUH",
                        f"{display_date(selected.get('developer_license_start_date'))} – {display_date(selected.get('developer_license_end_date'))}",
                    )
                    if permit_history:
                        st.markdown("**Previous advertising and sales permits · TEDUH**")
                        history_display = []
                        for row in permit_history:
                            history_display.append(
                                {
                                    "Permit": display_text(row.get("no_lesenpermit")),
                                    "Start": display_date(row.get("tarikh_mula")),
                                    "End": display_date(row.get("tarikh_luput")),
                                    "Period": display_text(row.get("tempoh")),
                                }
                            )
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
                        with st.container(key="manual_project_details"):
                            st.caption(
                                "These fields are maintained locally and do not come from TEDUH."
                            )
                            manual_columns = st.columns(
                                int(has_manual_launch) + int(has_manual_built_up) + int(has_manual_psf)
                            ) if has_manual_launch or has_manual_built_up or has_manual_psf else []
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

                with st.expander("Weekly progress and data provenance"):
                    timing = st.columns(2)
                    timing[0].metric(
                        "Retrieved from TEDUH · Application",
                        display_timestamp(selected.get("retrieved_at")),
                        help="Timestamp generated by this application when the API response was obtained.",
                    )
                    timing[1].metric(
                        "TEDUH displayed data through · TEDUH frontend",
                        display_date(selected.get("source_dataset_as_of")),
                        help="Portal-wide TEDUH frontend label; not an authoritative per-project API timestamp.",
                    )
                    if project_history.empty:
                        st.info("No dated observations have been stored for this project yet.")
                    else:
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
                                "This is the opening observation. Past sales dates cannot be reconstructed from TEDUH's current snapshot."
                            )
                        chart = weekly.set_index("week_start")[["Sales %", "Construction %"]].dropna(
                            axis=1, how="all"
                        )
                        if not chart.empty:
                            st.line_chart(chart, height=260)
                        weekly["Units sold display"] = weekly["Units sold"].map(whole_number)
                        weekly["Weekly units sold display"] = weekly["Weekly units sold"].map(signed_number)
                        weekly["Sales display"] = weekly["Sales %"].map(pct)
                        weekly["Sales change display"] = weekly["Sales change"].map(
                            lambda value: signed_number(value, decimals=1, suffix=" pp")
                        )
                        weekly["Construction display"] = weekly["Construction %"].map(pct)
                        weekly["Construction change display"] = weekly["Construction change"].map(
                            lambda value: signed_number(value, decimals=1, suffix=" pp")
                        )
                        st.dataframe(
                            weekly[
                                [
                                    "Week",
                                    "Units sold display",
                                    "Weekly units sold display",
                                    "Sales display",
                                    "Sales change display",
                                    "Construction display",
                                    "Construction change display",
                                    "Status",
                                ]
                            ],
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "Units sold display": "Units sold",
                                "Weekly units sold display": "Weekly units sold",
                                "Sales display": "Sales",
                                "Sales change display": "Sales change",
                                "Construction display": "Construction",
                                "Construction change display": "Construction change",
                            },
                        )

with all_projects_tab:
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
    st.divider()
    render_refresh_status_panel()
    st.divider()
    refresh_spacer, refresh_action = st.columns([3, 1])
    with refresh_action:
        refresh_clicked = st.button("Refresh TEDUH shortlist", type="primary", width="stretch")
    if refresh_clicked:
        progress_messages: list[str] = []
        refresh_progress = st.progress(0.0, text="Preparing TEDUH shortlist refresh…")

        def update_refresh_progress(
            completed: int,
            total: int,
            project_code: str,
            succeeded: bool,
        ) -> None:
            fraction = completed / total if total else 0.0
            refresh_progress.progress(
                fraction,
                text=f"Reviewed {completed}/{total} shortlist projects · {project_code}",
            )

        try:
            with st.spinner("Refreshing active projects sequentially from TEDUH…"):
                result = snapshot_shortlist(
                    SETTINGS,
                    progress=progress_messages.append,
                    project_progress=update_refresh_progress,
                )
            refresh_progress.progress(1.0, text="Refresh completed and validated")
            st.session_state["app_notice"] = (
                f"Refresh completed: {result['project_count']} projects and {result['alert_count']} alerts."
            )
            st.rerun()
        except Exception as exc:  # Streamlit must surface source failures without replacing valid output.
            st.session_state["app_error"] = str(exc)
            st.rerun()

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
