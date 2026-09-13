# Metric Definitions

These are analytical calculations, not official TEDUH financial or sales metrics.

## Controlled sales-status mapping

- Sold: `Dijual`, `Telah Dijual`, `sold`
- Unsold: `Belum Dijual`, `avail`, `available`, `unsold`
- Booked: `Tempahan`, `booked`, `booking`, `ditempah`
- Reserved: `reserved`, `reservation`, `rizab`
- Anything else: `unknown`, retained for investigation and excluded from the denominator

`statusJualan` is primary and the lower-level availability `status` is a fallback.

Booked/reserved and unknown counts remain internal validation inputs. They are omitted from the user-facing CSV and Parquet because both categories are zero in the observed eligible population. The pipeline still checks them so a future TEDUH vocabulary change cannot be silently treated as sold or unsold.

## Unit coverage

```text
unit_coverage_percentage = unit_records_count / reported_total_units × 100
```

The project-level reported total remains separate from the observed unit-row count.

## Sales percentage

```text
comparable_total_units = sold + unsold + booked + reserved
sales_percentage = sold / comparable_total_units × 100
```

Unknown statuses are excluded and reported separately. Bookings and reservations remain non-sold categories in the denominator. The result is labelled calculated, not official.

Confidence:

- `high`: exact unit reconciliation, no duplicate keys, and no unknown statuses
- `medium`: unit coverage between 95% and 105%, with no duplicate keys
- `low`: a denominator exists but coverage/reconciliation is weak
- `unavailable`: no comparable units

The 95% tolerance is a documented completeness boundary; it allows at most a 5% known shortfall/overage while preventing weak samples from being presented as project totals.

## Potential listed GDV

```text
potential_listed_gdv = sum(hargaJualan for observed units)
```

- `high`: exact unit reconciliation, 100% listed-price coverage, and no duplicate unit keys
- `medium`: unit coverage between 95% and 105%, at least 95% listed-price coverage, and no duplicates
- `low`: no unit-level total is presented; only a complete construction/type min-max indicative range is available
- `unavailable`: coverage conditions fail

This is potential listed GDV, not audited revenue or official developer GDV. A medium value remains the sum of observed prices and is not silently grossed up.

## Unit pricing

Only positive, parseable prices are included.

```text
average_listed_price_per_unit = mean(valid hargaJualan)
median_listed_price_per_unit = median(valid hargaJualan)
listed_price_p25 / listed_price_p75 = interpolated 25th / 75th percentiles
average_recorded_spa_price_per_unit = mean(valid sold-unit hargaSPJB)
median_recorded_spa_price_per_unit = median(valid sold-unit hargaSPJB)
```

The median listed price is the primary typical-unit measure. The 25th–75th percentile range describes the middle half of the project without removing high- or low-priced units from potential listed GDV. Recorded-SPA measures remain subject to `spa_price_coverage_percentage`.

## Recorded SPA sales value

```text
recorded_spa_sales_value = sum(hargaSPJB for sold units where SPA price exists)
```

If sold units exist but none has an SPA price, the value is null rather than zero. SPA coverage is reported as sold units with SPA price divided by sold units.

## Estimated sold value

```text
estimated_sold_value = sum(COALESCE(hargaSPJB, hargaJualan)) for sold units
```

The metric is withheld when any sold unit has neither price. It explicitly mixes recorded SPA prices with listed-price substitutes and must be labelled an estimate.

Sales-value confidence:

- `high`: complete unit reconciliation and 100% SPA coverage, or no sold units in a fully reconciled project
- `medium`: near-complete units and every sold unit has either SPA or listed price
- `low`: only a partial recorded or estimated value is available
- `unavailable`: neither value can be supported

## Remaining listed value

```text
remaining_listed_value = sum(hargaJualan for unsold, booked, and reserved units)
```

All included units must have a listed price and project unit coverage must be at least 95%. Bookings and reservations are not counted as sold.

## Construction percentage

```text
construction_percentage = sum(peratus × row_unit_count) / sum(row_unit_count)
```

The calculation is made only when:

- every row has a valid unit count and percentage from 0 to 100;
- the type/floor/room/bathroom/area grouping key is unique; and
- when a reported project total exists, construction-row units reconcile exactly to it.

If those checks fail, component rows remain in `construction_rows_json` and the aggregate is null. Exact reconciliation gives `high` confidence; valid rows without a reported total give `medium` confidence.

## Indicative GDV range

```text
minimum_indicative_gdv = sum(row_units × row_minimum_price)
maximum_indicative_gdv = sum(row_units × row_maximum_price)
```

Rows must be unique, prices complete, and units reconciled. No midpoint is calculated.
