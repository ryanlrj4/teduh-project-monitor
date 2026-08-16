# Data Dictionary

Blank normalized values mean the source was blank, displayed `-`, could not be parsed safely, or did not support the field. Missing monetary values are never changed to zero.

## Local shortlist fields

These fields are entered locally and are not claimed to come from TEDUH.

| Field | Type | Meaning |
|---|---|---|
| `region` | text | Controlled dashboard region; currently `Kuala Lumpur` or `Penang` |
| `display_name` | text | Actual or preferred project name shown in the dashboard |
| `parent_group` | text | Public parent-group mapping maintained by the user |
| `project_set` | text | `reporting_set`, `comparator_set`, or `general` |
| `manual_launch_date` | date | Optional locally entered launch date, kept separate from TEDUH's First SPA date and hidden when blank |
| `manual_built_up_min_sqft`, `manual_built_up_max_sqft` | decimal sqft | Optional locally entered built-up range; hidden in project details when blank |
| `manual_psf_min`, `manual_psf_max` | decimal RM/sqft | Optional locally entered PSF range; hidden in project details when blank |
| `priority` | text | `high`, `medium`, or `low` |
| `tracking_notes` | text | Optional local monitoring note |
| `shortlist_active` | Yes/No | Whether the project is included in a normal refresh |
| `shortlist_origin` | text | Provenance of the shortlist entry, separate from TEDUH provenance |

## Project and developer identity

| Original field | Normalized field | Source response | Type | Meaning / observed values | Null handling | Example |
|---|---|---|---|---|---|---|
| `projek.kod_projek` / search `id` | `source_project_id` | project detail/search | text | KPKT project code and stable project key | Required; pipeline error if missing | `31274-1` |
| `projek.nama` | `project_name` | project detail | text | Project name | Retain null | `Aosis Mont Kiara` |
| `pemaju.kod_pemaju` | `developer_id` | project detail | text | Explicit developer code; never derived from project name | Retain null | `31274` |
| `pemaju.nama` | `developer_name` | project detail | text | Registered developer name | Whitespace normalized | `MODERN PLUS SDN. BHD.` |

## Location and permit

| Original field | Normalized field | Source response | Type | Meaning | Null handling | Example |
|---|---|---|---|---|---|---|
| `projek.negeri` | `state` | project detail | text | Project state; primary KL filter comes from search `state=14` | Standardize harmless case only | `Wp Kuala Lumpur` |
| `projek.daerah` | `district` | project detail | text | Project district | `-` becomes null | `Kuala Lumpur` |
| `kod_bandar_id` plus city lookup | `city` | search/lookup | text | TEDUH administrative city label | Missing code becomes null | `Mukim Kuala Lumpur` |
| Same location fields | `source_*_value` | detail/lookup | text | Original cleaned source label retained for traceability | Retain null | `Wp Kuala Lumpur` |
| `projek.permitNo` | `permit_number` | project detail | text | Current advertising and sales permit | Retain null | `31274-1/04-2029/0279(N)-(S)` |
| `projek.permitMula` | `permit_start_date` | project detail | date | Permit start date | Invalid/`-` becomes null | `2026-04-10` |
| `projek.permitTamat` | `permit_end_date` | project detail | date | Permit end date | Invalid/`-` becomes null | `2029-04-09` |
| `pjb.tarikhPjbPertama` | `first_spa_date` | project detail | date | First PJB/SPA date | Invalid/`-` becomes null | `2026-05-10` |
| `status.rows[].hargaMin`, `status.rows[].hargaMax` | `teduh_spa_price_min`, `teduh_spa_price_max` | project detail | decimal RM | Minimum and maximum prices displayed in TEDUH's component-status table | Withheld if either side is unavailable | `805200.00`, `2482800.00` |
| First SPA, else permit start | `hims_project_reference_date` | derived | date | Project-age proxy used for HIMS eligibility | Project is excluded if no reference date exists | `2026-05-10` |
| Reference-date selection | `hims_project_reference_date_basis` | derived | text | `first_spa_date` or `permit_start_date_fallback` | Required in published rows | `first_spa_date` |
| Fixed source boundary | `hims_eligibility_cutoff_date` | configuration | date | Earliest eligible reference date | Always `2022-01-31` | `2022-01-31` |

## PJB and construction

| Original field | Normalized field | Source response | Type | Meaning | Null handling | Example |
|---|---|---|---|---|---|---|
| `status.keseluruhan` | `project_status` | project detail | text | Overall status such as Belum Mula, Lancar, Sakit, Lewat, Siap Dengan CCC, or Siap Dengan CFO | Search status used as fallback | `Lancar` |
| `pjb.serahKosongIkutPjb` | `expected_vp_date` | project detail | date | Original vacant-possession date | `-` becomes null | `2028-01-01` |
| `pjb.serahKosongBaharuIkutPjbPertama` | `revised_vp_date` | project detail | date | Revised vacant-possession date | `-` becomes null | `2029-01-01` |
| `status.keseluruhan` / `status.rows[].ccc` / `status.rows[].komponen` | `ccc_obtained` | project detail | text | `Yes` for an overall completed-with-CCC/CFO status or explicit component CCC/CFO evidence; otherwise `No` | Always `Yes` or `No` | `Yes` |
| `status.rows[].ccc` | `ccc_date` | project detail | date | Latest valid CCC/CFO date across the project's component rows | `-` or invalid values become null | `2026-02-23` |
| `status.rows[].vp` | `vp_date` | project detail | date | Latest valid VP date across the project's component rows | `-` or invalid values become null | `2026-03-31` |
| `status.rows[].peratus` | `construction_percentage` | project detail | decimal percent | Unit-weighted construction percentage when rows safely partition units | Otherwise null with reason | `10.59` |
| `status.rows[]` | `construction_rows_json` | project detail | JSON text | Original construction/type rows for traceability | Empty list retained | `[...]` |

## Units, sales, coverage, and values

| Original/derived input | Normalized field | Type | Meaning | Null handling |
|---|---|---|---|---|
| `unitSummary.unit` | `reported_total_units` | integer | Project-level unit total reported by TEDUH | Retain null |
| Count of `unitGroups[].units[]` | `unit_records_count` | integer | Individual unit rows received | Zero remains zero and is investigated |
| Parseable `hargaJualan` count | `priced_unit_records_count` | integer | Unit rows with listed prices | Count only parseable values |
| `statusJualan` with `status` fallback | `sold_units`, `unsold_units` | integer | User-facing counts using the controlled mapping | Missing unit endpoints do not become business facts |
| Booked/reserved/unknown controlled mapping | Internal QA counters | integer | Safeguards against silently misclassifying future status values | Checked and reported in data-quality documentation; omitted from public tables |
| Known classes | `comparable_total_units` | integer | Denominator for calculated sales percentage | Unknown classes excluded |
| Sold / comparable | `sales_percentage` | decimal percent | Calculated, not an official TEDUH percentage | Null for zero denominator |
| Sum of qualifying `hargaJualan` | `potential_listed_gdv` | decimal RM | Potential listed value under coverage rules | Withheld when rules fail |
| Sold `hargaSPJB` | `recorded_spa_sales_value` | decimal RM | Sum of recorded sold-unit SPA prices | Null if sold units exist but none has SPA price |
| Sold `COALESCE(hargaSPJB,hargaJualan)` | `estimated_sold_value` | decimal RM | Disclosed estimate using listed price fallback | Null if a sold unit has neither price |
| Non-sold `hargaJualan` | `remaining_listed_value` | decimal RM | Listed value of unsold/booked/reserved units | Withheld when coverage fails |
| Construction row units × min/max price | `minimum_indicative_gdv`, `maximum_indicative_gdv` | decimal RM | Strict indicative range | Null unless rows partition units and prices are complete |
| Observed / reported units | `unit_coverage_percentage` | decimal percent | Reconciliation coverage | Null for missing/zero denominator |
| Priced / observed units | `listed_price_coverage_percentage` | decimal percent | Listed-price coverage | Null for zero observed units |
| Sold with SPA / sold | `spa_price_coverage_percentage` | decimal percent | SPA coverage among sold units | Null when there are no sold units |

## Quality, confidence, and provenance

| Normalized field | Type | Meaning |
|---|---|---|
| `duplicate_unit_identifiers` | integer | Extra occurrences of duplicate `(pembangunan_id, no)` keys |
| `construction_row_units` | integer | Sum of units represented by construction rows |
| `construction_row_count` | integer | Construction/type row count |
| `gdv_confidence` | text | `high`, `medium`, `low`, or `unavailable` |
| `sales_percentage_confidence` | text | Confidence in the calculated sales denominator |
| `sales_value_confidence` | text | Confidence in SPA/estimated sold values |
| `construction_confidence` | text | Confidence in construction aggregation |
| `construction_note` | text | Reason construction was withheld |
| `source_url` | text | Official TEDUH search page |
| `source_detail_api_url` | text | Exact project detail request |
| `source_units_api_url` | text | Exact unit request |
| `snapshot_date` | date | Local observation date |
| `source_dataset_as_of` | date | Previous-day label displayed by TEDUH frontend |
| `source_dataset_as_of_method` | text | Warning explaining that the label is not an API timestamp |
| `retrieved_at` | timestamp text | Local retrieval time with timezone |
| `transformation_version` | text | Version of the normalization/calculation rules |
