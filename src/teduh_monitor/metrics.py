from __future__ import annotations

import json
import math
from collections import Counter
from decimal import Decimal
from statistics import median
from typing import Any

from .config import HIMS_UNIT_DATA_START_ISO, SEARCH_PAGE_URL, TRANSFORMATION_VERSION
from .normalize import (
    clean_text,
    hims_project_reference,
    iso_or_none,
    normalize_sales_status,
    normalize_state,
    parse_price,
    safe_percentage,
    to_int,
)


def price_percentile(values: list[Decimal], percentile: float) -> Decimal | None:
    """Return a linearly interpolated percentile for a non-empty price series."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = Decimal(str(position - lower_index))
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


def flatten_units(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    if not payload:
        return flattened
    for group in payload.get("unitGroups") or []:
        development_id = group.get("pembangunan_id")
        group_type = group.get("jenis")
        for unit in group.get("units") or []:
            row = dict(unit)
            row["pembangunan_id"] = development_id
            row["group_jenis"] = group_type
            flattened.append(row)
    return flattened


def is_bumi_unit(unit: dict[str, Any]) -> bool:
    explicit = unit.get("kuota")
    if isinstance(explicit, bool):
        return explicit
    if str(explicit or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "ya",
        "bumi",
        "bumiputera",
    }:
        return True
    return str(unit.get("kuotaBumi") or "").strip().casefold() in {"yes", "ya"}


def remaining_inventory_summary(
    units: list[dict[str, Any]],
    classifications: list[str],
) -> list[dict[str, Any]]:
    """Summarise non-sold inventory by TEDUH component, property type, and quota."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for unit, status_class in zip(units, classifications):
        if status_class not in {"unsold", "booked", "reserved"}:
            continue
        key = (
            clean_text(unit.get("pembangunan_id")) or "",
            clean_text(unit.get("group_jenis")) or "Unspecified",
            "Bumiputera" if is_bumi_unit(unit) else "Non-Bumiputera",
        )
        grouped.setdefault(key, []).append(unit)

    rows: list[dict[str, Any]] = []
    for (component_id, property_type, quota_category), inventory in grouped.items():
        prices = [parse_price(unit.get("hargaJualan")) for unit in inventory]
        known_prices = [price for price in prices if price is not None]
        rows.append(
            {
                "source_component_id": component_id,
                "property_type": property_type,
                "quota_category": quota_category,
                "units": len(inventory),
                "listed_value": (
                    sum(known_prices, Decimal("0"))
                    if len(known_prices) == len(inventory)
                    else None
                ),
                "minimum_listed_price": min(known_prices) if known_prices else None,
                "maximum_listed_price": max(known_prices) if known_prices else None,
                "listed_price_coverage_percentage": safe_percentage(
                    len(known_prices), len(inventory)
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            str(row["property_type"]).casefold(),
            str(row["source_component_id"]),
            str(row["quota_category"]),
        )
    )
    return rows


def component_sales_summary(
    payload: dict[str, Any] | None,
    reported_total_units: int | None,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Summarise sales independently for each TEDUH unit group.

    TEDUH consistently supplies a component identifier but does not always
    supply a human-readable block name. Fallback labels therefore remain
    deliberately neutral rather than inferring a tower from unit numbers.
    """
    groups = (payload or {}).get("unitGroups") or []
    if not groups:
        return [], "unavailable", "No TEDUH unit groups"

    summaries: list[dict[str, Any]] = []
    all_units: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        units = [dict(unit) for unit in group.get("units") or []]
        development_id = group.get("pembangunan_id")
        for unit in units:
            unit["pembangunan_id"] = development_id
        all_units.extend(units)
        classes = [
            normalize_sales_status(unit.get("statusJualan"), unit.get("status"))
            for unit in units
        ]
        counts = Counter(classes)
        sold = counts["sold"]
        unsold = counts["unsold"]
        booked = counts["booked"] + counts["reserved"]
        unknown = counts["unknown"]
        comparable = sold + unsold + booked
        duplicate_count = duplicate_unit_count(units)
        explicit_label = clean_text(
            group.get("nama")
            or group.get("nama_blok")
            or group.get("blok")
            or group.get("block")
            or group.get("tower")
            or group.get("fasa")
        )
        confidence = (
            "high"
            if units and unknown == 0 and duplicate_count == 0 and comparable == len(units)
            else "low"
            if comparable
            else "unavailable"
        )
        summaries.append(
            {
                "component_number": index,
                "component_label": explicit_label or f"Component {index}",
                "source_component_id": clean_text(development_id),
                "property_type": clean_text(group.get("jenis")),
                "total_units": len(units),
                "sold_units": sold,
                "unsold_units": unsold,
                "booked_or_reserved_units": booked,
                "unknown_sales_status_units": unknown,
                "comparable_total_units": comparable,
                "sales_percentage": safe_percentage(sold, comparable),
                "duplicate_unit_identifiers": duplicate_count,
                "confidence": confidence,
            }
        )

    observed_total = sum(row["total_units"] for row in summaries)
    duplicate_count = duplicate_unit_count(all_units)
    unknown_count = sum(row["unknown_sales_status_units"] for row in summaries)
    notes: list[str] = []
    if reported_total_units is not None and observed_total != reported_total_units:
        notes.append(
            f"Component units ({observed_total}) do not reconcile to reported units ({reported_total_units})"
        )
    if duplicate_count:
        notes.append(f"{duplicate_count} duplicate unit identifier(s) detected")
    if unknown_count:
        notes.append(f"{unknown_count} unit(s) have an unknown sales status")
    row_confidences = {str(row.get("confidence") or "unavailable") for row in summaries}
    if not notes and row_confidences == {"high"}:
        confidence = "high"
    elif any(row.get("comparable_total_units") for row in summaries):
        confidence = "low"
    else:
        confidence = "unavailable"
        notes.append("No comparable unit sales statuses")
    return summaries, confidence, "; ".join(notes) or None


def duplicate_unit_count(units: list[dict[str, Any]]) -> int:
    keys = [
        (str(unit.get("pembangunan_id") or ""), str(unit.get("no") or "").strip())
        for unit in units
    ]
    counts = Counter(key for key in keys if key[1])
    return sum(count - 1 for count in counts.values() if count > 1)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def weighted_construction(
    rows: list[dict[str, Any]], reported_total_units: int | None
) -> tuple[float | None, str, str | None, int | None]:
    if not rows:
        return None, "unavailable", "No construction rows", None
    parsed: list[tuple[tuple[str, ...], int, Decimal]] = []
    for row in rows:
        unit_count = to_int(row.get("unit"))
        percentage = parse_price(row.get("peratus"))
        if unit_count is None or unit_count < 0 or percentage is None:
            return None, "unavailable", "Missing unit count or percentage", None
        if percentage < 0 or percentage > 100:
            return None, "unavailable", "Construction percentage outside 0-100", None
        key = tuple(
            str(row.get(field) or "").strip().casefold()
            for field in ("jenis", "tingkat", "bilik", "tandas", "keluasan")
        )
        parsed.append((key, unit_count, percentage))
    keys = [item[0] for item in parsed]
    if len(keys) != len(set(keys)):
        return None, "unavailable", "Potential double-counted construction groups", None
    row_units = sum(item[1] for item in parsed)
    if row_units <= 0:
        return None, "unavailable", "Construction rows have zero units", row_units
    if reported_total_units is not None and row_units != reported_total_units:
        return (
            None,
            "unavailable",
            f"Construction row units ({row_units}) do not reconcile to reported units ({reported_total_units})",
            row_units,
        )
    weighted = sum(percentage * unit_count for _, unit_count, percentage in parsed) / row_units
    confidence = "high" if reported_total_units is not None else "medium"
    return round(float(weighted), 6), confidence, None, row_units


def indicative_gdv_range(
    rows: list[dict[str, Any]], reported_total_units: int | None
) -> tuple[Decimal | None, Decimal | None]:
    if not rows:
        return None, None
    keys: set[tuple[str, ...]] = set()
    minimum = Decimal("0")
    maximum = Decimal("0")
    total_units = 0
    for row in rows:
        key = tuple(
            str(row.get(field) or "").strip().casefold()
            for field in ("jenis", "tingkat", "bilik", "tandas", "keluasan")
        )
        units = to_int(row.get("unit"))
        price_min = parse_price(row.get("hargaMin"))
        price_max = parse_price(row.get("hargaMax"))
        if key in keys or units is None or units < 0 or price_min is None or price_max is None:
            return None, None
        keys.add(key)
        total_units += units
        minimum += price_min * units
        maximum += price_max * units
    if reported_total_units is not None and total_units != reported_total_units:
        return None, None
    return minimum, maximum


def teduh_spa_price_range(
    rows: list[dict[str, Any]],
) -> tuple[Decimal | None, Decimal | None]:
    """Return the price range displayed in TEDUH's component-status table."""
    minimums: list[Decimal] = []
    maximums: list[Decimal] = []
    for row in rows:
        minimum = parse_price(row.get("hargaMin"))
        maximum = parse_price(row.get("hargaMax"))
        if minimum is not None:
            minimums.append(minimum)
        if maximum is not None:
            maximums.append(maximum)
    if not minimums or not maximums:
        return None, None
    return min(minimums), max(maximums)


def ccc_obtained(rows: list[dict[str, Any]], overall_status: Any = None) -> str:
    """Return Yes when TEDUH reports project-level or component CCC/CFO evidence."""
    status = (clean_text(overall_status) or "").casefold()
    if "siap dengan ccc" in status or "siap dengan cfo" in status:
        return "Yes"
    for row in rows:
        if clean_text(row.get("ccc")):
            return "Yes"
        component = (clean_text(row.get("komponen")) or "").casefold()
        if "siap dengan ccc" in component or "siap dengan cfo" in component:
            return "Yes"
    return "No"


def component_completion_dates(
    rows: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Return the latest valid CCC/CFO and VP dates reported by any component."""
    ccc_dates = [iso_or_none(row.get("ccc")) for row in rows]
    vp_dates = [iso_or_none(row.get("vp")) for row in rows]
    valid_ccc_dates = [value for value in ccc_dates if value]
    valid_vp_dates = [value for value in vp_dates if value]
    return (
        max(valid_ccc_dates) if valid_ccc_dates else None,
        max(valid_vp_dates) if valid_vp_dates else None,
    )


def calculate_project_metrics(
    *,
    search_project: dict[str, Any],
    detail: dict[str, Any] | None,
    units_payload: dict[str, Any] | None,
    snapshot_date: str,
    source_dataset_as_of: str,
    retrieved_at: str,
) -> dict[str, Any]:
    project_code = str(search_project.get("id") or "").strip()
    detail = detail or {}
    project = detail.get("projek") or {}
    developer = detail.get("pemaju") or search_project.get("pemaju") or {}
    summary = detail.get("unitSummary") or {}
    pjb = detail.get("pjb") or {}
    status = detail.get("status") or {}
    construction_rows = status.get("rows") or []
    units = flatten_units(units_payload)
    duplicate_units = duplicate_unit_count(units)

    reported_total = to_int(summary.get("unit"))
    component_sales, component_sales_confidence, component_sales_note = component_sales_summary(
        units_payload, reported_total
    )
    unit_count = len(units)
    priced_units = [
        unit
        for unit in units
        if (price := parse_price(unit.get("hargaJualan"))) is not None and price > 0
    ]
    classifications = [
        normalize_sales_status(unit.get("statusJualan"), unit.get("status")) for unit in units
    ]
    class_counts = Counter(classifications)
    sold_units = class_counts["sold"]
    unsold_units = class_counts["unsold"]
    booked_units = class_counts["booked"] + class_counts["reserved"]
    unknown_units = class_counts["unknown"]
    comparable_total = sold_units + unsold_units + booked_units

    sold_rows = [unit for unit, status_class in zip(units, classifications) if status_class == "sold"]
    sold_with_spa = [
        unit
        for unit in sold_rows
        if (price := parse_price(unit.get("hargaSPJB"))) is not None and price > 0
    ]
    unit_coverage = safe_percentage(unit_count, reported_total)
    listed_coverage = safe_percentage(len(priced_units), unit_count)
    spa_coverage = safe_percentage(len(sold_with_spa), sold_units)
    sales_percentage = safe_percentage(sold_units, comparable_total)

    exact_unit_reconciliation = reported_total is not None and unit_count == reported_total
    near_unit_reconciliation = (
        unit_coverage is not None and 95 <= unit_coverage <= 105
    )
    exact_listed_coverage = listed_coverage == 100.0
    near_listed_coverage = listed_coverage is not None and listed_coverage >= 95

    listed_values = [parse_price(unit.get("hargaJualan")) for unit in units]
    positive_listed_values = [
        value for value in listed_values if value is not None and value > 0
    ]
    average_listed_price_per_unit = (
        sum(positive_listed_values, Decimal("0")) / len(positive_listed_values)
        if positive_listed_values
        else None
    )
    median_listed_price_per_unit = (
        median(positive_listed_values) if positive_listed_values else None
    )
    listed_price_p25 = price_percentile(positive_listed_values, 0.25)
    listed_price_p75 = price_percentile(positive_listed_values, 0.75)
    potential_listed_gdv: Decimal | None = None
    gdv_confidence = "unavailable"
    if units and duplicate_units == 0 and exact_unit_reconciliation and exact_listed_coverage:
        potential_listed_gdv = sum((value for value in listed_values if value is not None), Decimal("0"))
        gdv_confidence = "high"
    elif units and duplicate_units == 0 and near_unit_reconciliation and near_listed_coverage:
        potential_listed_gdv = sum((value for value in listed_values if value is not None), Decimal("0"))
        gdv_confidence = "medium"

    minimum_indicative_gdv, maximum_indicative_gdv = indicative_gdv_range(
        construction_rows, reported_total
    )
    if gdv_confidence == "unavailable" and minimum_indicative_gdv is not None:
        gdv_confidence = "low"

    if sold_units == 0 and exact_unit_reconciliation:
        recorded_spa_sales_value: Decimal | None = Decimal("0")
        estimated_sold_value: Decimal | None = Decimal("0")
        sold_listed_value: Decimal | None = Decimal("0")
    elif sold_units == 0:
        # With incomplete or absent unit rows, zero observed sales is not proof
        # of zero project sales or value.
        recorded_spa_sales_value = None
        estimated_sold_value = None
        sold_listed_value = None
    else:
        spa_values = [
            price
            if (price := parse_price(unit.get("hargaSPJB"))) is not None and price > 0
            else None
            for unit in sold_rows
        ]
        recorded_spa_sales_value = (
            sum((value for value in spa_values if value is not None), Decimal("0"))
            if any(value is not None for value in spa_values)
            else None
        )
        estimated_values = [
            parse_price(unit.get("hargaSPJB")) or parse_price(unit.get("hargaJualan"))
            for unit in sold_rows
        ]
        estimated_sold_value = (
            sum((value for value in estimated_values if value is not None), Decimal("0"))
            if all(value is not None for value in estimated_values)
            else None
        )
        sold_listed_prices = [parse_price(unit.get("hargaJualan")) for unit in sold_rows]
        sold_listed_value = (
            sum((value for value in sold_listed_prices if value is not None), Decimal("0"))
            if all(value is not None for value in sold_listed_prices)
            else None
        )

    if exact_unit_reconciliation and duplicate_units == 0 and unknown_units == 0:
        sales_percentage_confidence = "high"
    elif near_unit_reconciliation and duplicate_units == 0:
        sales_percentage_confidence = "medium"
    elif comparable_total:
        sales_percentage_confidence = "low"
    else:
        sales_percentage_confidence = "unavailable"

    if sold_units == 0 and exact_unit_reconciliation:
        sales_value_confidence = "high"
    elif sold_units and spa_coverage == 100.0 and exact_unit_reconciliation and duplicate_units == 0:
        sales_value_confidence = "high"
    elif sold_units and estimated_sold_value is not None and near_unit_reconciliation:
        sales_value_confidence = "medium"
    elif recorded_spa_sales_value is not None or estimated_sold_value is not None:
        sales_value_confidence = "low"
    else:
        sales_value_confidence = "unavailable"

    non_sold_rows = [
        unit
        for unit, status_class in zip(units, classifications)
        if status_class in {"unsold", "booked", "reserved"}
    ]
    non_sold_prices = [parse_price(unit.get("hargaJualan")) for unit in non_sold_rows]
    if non_sold_rows and all(value is not None for value in non_sold_prices) and near_unit_reconciliation:
        remaining_listed_value: Decimal | None = sum(
            (value for value in non_sold_prices if value is not None), Decimal("0")
        )
    elif not non_sold_rows and comparable_total > 0:
        remaining_listed_value = Decimal("0")
    else:
        remaining_listed_value = None

    construction_percentage, construction_confidence, construction_note, construction_row_units = (
        weighted_construction(construction_rows, reported_total)
    )
    value_sold_percentage = (
        round(float(estimated_sold_value / potential_listed_gdv * 100), 6)
        if estimated_sold_value is not None
        and potential_listed_gdv is not None
        and potential_listed_gdv > 0
        and gdv_confidence in {"high", "medium"}
        and sales_value_confidence in {"high", "medium"}
        else None
    )
    sales_construction_gap = (
        round(float(sales_percentage - construction_percentage), 6)
        if sales_percentage is not None and construction_percentage is not None
        else None
    )

    price_pairs = [
        (parse_price(unit.get("hargaJualan")), parse_price(unit.get("hargaSPJB")))
        for unit in sold_rows
    ]
    complete_price_pairs = [
        (listed, spa)
        for listed, spa in price_pairs
        if listed is not None and listed > 0 and spa is not None and spa > 0
    ]
    paired_listed_value = sum((listed for listed, _ in complete_price_pairs), Decimal("0"))
    paired_spa_value = sum((spa for _, spa in complete_price_pairs), Decimal("0"))
    recorded_price_realisation_percentage = (
        round(float(paired_spa_value / paired_listed_value * 100), 6)
        if paired_listed_value > 0
        else None
    )
    recorded_discounts = [
        float((Decimal("1") - (spa / listed)) * 100)
        for listed, spa in complete_price_pairs
    ]
    median_recorded_discount_percentage = (
        round(median(recorded_discounts), 6) if recorded_discounts else None
    )
    positive_spa_values = [
        price
        for unit in sold_rows
        if (price := parse_price(unit.get("hargaSPJB"))) is not None and price > 0
    ]
    average_recorded_spa_price_per_unit = (
        sum(positive_spa_values, Decimal("0")) / len(positive_spa_values)
        if positive_spa_values
        else None
    )
    median_recorded_spa_price_per_unit = (
        median(positive_spa_values) if positive_spa_values else None
    )

    bumi_rows = [unit for unit in units if is_bumi_unit(unit)]
    bumi_classes = [
        normalize_sales_status(unit.get("statusJualan"), unit.get("status"))
        for unit in bumi_rows
    ]
    bumi_counts = Counter(bumi_classes)
    bumi_sold_units = bumi_counts["sold"]
    bumi_unsold_units = (
        bumi_counts["unsold"] + bumi_counts["booked"] + bumi_counts["reserved"]
    )
    bumi_comparable_units = bumi_sold_units + bumi_unsold_units
    bumi_sales_percentage = safe_percentage(bumi_sold_units, bumi_comparable_units)
    remaining_inventory = remaining_inventory_summary(units, classifications)
    teduh_spa_price_min, teduh_spa_price_max = teduh_spa_price_range(construction_rows)
    ccc_date, vp_date = component_completion_dates(construction_rows)

    latest_licence = developer.get("latest_lesen") or search_project.get("latest_lesen") or {}
    project_state = project.get("negeri")
    district_value = project.get("daerah")
    permit_start_date = iso_or_none(project.get("permitMula") or latest_licence.get("tarikh_mula"))
    first_spa_date = iso_or_none(pjb.get("tarikhPjbPertama"))
    hims_reference_date, hims_reference_basis = hims_project_reference(
        pjb.get("tarikhPjbPertama"),
        project.get("permitMula") or latest_licence.get("tarikh_mula"),
    )

    result = {
        "snapshot_date": snapshot_date,
        "source": "TEDUH",
        "source_project_id": project_code,
        "project_name": clean_text(project.get("nama") or search_project.get("nama")),
        "developer_id": clean_text(developer.get("kod_pemaju") or search_project.get("kod_pemaju")),
        "developer_name": clean_text(developer.get("nama")),
        "developer_status": clean_text(developer.get("statusPemaju")),
        "developer_project_count": to_int(developer.get("bilanganProjek")),
        "developer_license_number": clean_text(latest_licence.get("no_lesenpermit")),
        "developer_license_start_date": iso_or_none(latest_licence.get("tarikh_mula")),
        "developer_license_end_date": iso_or_none(latest_licence.get("tarikh_luput")),
        "state": normalize_state(project_state) or "Wp Kuala Lumpur",
        "district": clean_text(district_value),
        "project_location": clean_text(detail.get("lokasi")),
        "latitude": _float_or_none(detail.get("lat")),
        "longitude": _float_or_none(detail.get("lng")),
        "source_state_value": clean_text(project_state),
        "source_district_value": clean_text(district_value),
        "permit_number": clean_text(project.get("permitNo") or latest_licence.get("no_lesenpermit")),
        "permit_start_date": permit_start_date,
        "permit_end_date": iso_or_none(project.get("permitTamat") or latest_licence.get("tarikh_luput")),
        "first_spa_date": first_spa_date,
        "teduh_spa_price_min": teduh_spa_price_min,
        "teduh_spa_price_max": teduh_spa_price_max,
        "hims_project_reference_date": hims_reference_date,
        "hims_project_reference_date_basis": hims_reference_basis,
        "hims_eligibility_cutoff_date": HIMS_UNIT_DATA_START_ISO,
        "project_status": clean_text(status.get("keseluruhan"))
        or clean_text((search_project.get("status_project") or {}).get("keterangan")),
        "development_type": clean_text(status.get("maklumatPembangunan")),
        "agreement_type": clean_text(pjb.get("jenis")),
        "original_construction_period": clean_text(pjb.get("tempohAsal")),
        "expected_vp_date": iso_or_none(pjb.get("serahKosongIkutPjb")),
        "vp_period_amended": clean_text(pjb.get("pindaanTempohSerahKosong")),
        "approved_extension_period": clean_text(pjb.get("tempohTambahanDiluluskan")),
        "revised_construction_period": clean_text(pjb.get("tempohPembinaanBaharu")),
        "revised_vp_date": iso_or_none(pjb.get("serahKosongBaharuIkutPjbPertama")),
        "ccc_obtained": ccc_obtained(construction_rows, status.get("keseluruhan")),
        "ccc_date": ccc_date,
        "vp_date": vp_date,
        "reported_total_units": reported_total,
        "unit_records_count": unit_count,
        "priced_unit_records_count": len(priced_units),
        "sold_units": sold_units,
        "unsold_units": unsold_units,
        "booked_or_reserved_units": booked_units,
        "unknown_sales_status_units": unknown_units,
        "comparable_total_units": comparable_total,
        "sales_percentage": sales_percentage,
        "value_sold_percentage": value_sold_percentage,
        "sales_construction_gap": sales_construction_gap,
        "construction_percentage": construction_percentage,
        "potential_listed_gdv": potential_listed_gdv,
        "average_listed_price_per_unit": average_listed_price_per_unit,
        "median_listed_price_per_unit": median_listed_price_per_unit,
        "listed_price_p25": listed_price_p25,
        "listed_price_p75": listed_price_p75,
        "sold_listed_value": sold_listed_value,
        "recorded_spa_sales_value": recorded_spa_sales_value,
        "average_recorded_spa_price_per_unit": average_recorded_spa_price_per_unit,
        "median_recorded_spa_price_per_unit": median_recorded_spa_price_per_unit,
        "estimated_sold_value": estimated_sold_value,
        "remaining_listed_value": remaining_listed_value,
        "recorded_price_realisation_percentage": recorded_price_realisation_percentage,
        "median_recorded_discount_percentage": median_recorded_discount_percentage,
        "bumi_total_units": len(bumi_rows),
        "bumi_sold_units": bumi_sold_units,
        "bumi_unsold_units": bumi_unsold_units,
        "bumi_sales_percentage": bumi_sales_percentage,
        "minimum_indicative_gdv": minimum_indicative_gdv,
        "maximum_indicative_gdv": maximum_indicative_gdv,
        "unit_coverage_percentage": unit_coverage,
        "listed_price_coverage_percentage": listed_coverage,
        "spa_price_coverage_percentage": spa_coverage,
        "duplicate_unit_identifiers": duplicate_units,
        "construction_row_units": construction_row_units,
        "construction_row_count": len(construction_rows),
        "gdv_confidence": gdv_confidence,
        "sales_percentage_confidence": sales_percentage_confidence,
        "sales_value_confidence": sales_value_confidence,
        "construction_confidence": construction_confidence,
        "construction_note": construction_note,
        "component_sales_count": len(component_sales),
        "component_sales_confidence": component_sales_confidence,
        "component_sales_note": component_sales_note,
        "source_url": SEARCH_PAGE_URL,
        "source_detail_api_url": f"https://teduh.kpkt.gov.my/api/projek-swasta/{project_code}",
        "source_units_api_url": f"https://teduh.kpkt.gov.my/api/unit-projek-swasta/{project_code}",
        "source_dataset_as_of": source_dataset_as_of,
        "source_dataset_as_of_method": "TEDUH frontend previous-day label; not an API timestamp",
        "retrieved_at": retrieved_at,
        "transformation_version": TRANSFORMATION_VERSION,
        "construction_rows_json": json.dumps(construction_rows, ensure_ascii=False, separators=(",", ":")),
        "component_sales_json": json.dumps(component_sales, ensure_ascii=False, separators=(",", ":")),
        "remaining_inventory_json": json.dumps(
            remaining_inventory,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ),
        "permit_history_json": json.dumps(detail.get("lesen_records") or [], ensure_ascii=False, separators=(",", ":")),
    }
    return result
