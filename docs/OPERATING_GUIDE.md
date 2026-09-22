# TEDUH Project Monitor Operating Guide

## What the monitor does

The application is a focused local monitor:

1. Start with the authorized Kuala Lumpur comparison set and selected reporting-set projects in other regions.
2. Refresh only projects marked active.
3. Save one observation per project per local calendar day.
4. Show current metrics, dated history, and risk alerts.
5. Let the user add or edit projects without changing Python code.

The shortlist can be refreshed manually. The `refresh-if-due` command is intended for a Monday scheduler and makes no request if the current week already has a successful observation.

## Adding or editing a project

Open **Add or edit** in the dashboard.

The Parent group field is searchable and suggests groups already used by the tracked library. Select an existing group to keep naming consistent, or type a new group when it is not yet listed. Project and group finders elsewhere in the dashboard use the same searchable-selector pattern.

- **TEDUH project code** is the public stable key, for example `30031-1`.
- **Region** is detected from TEDUH when a new project is saved. Existing projects without a valid observation are checked again on save, so an initially incorrect region can be corrected automatically.
- **Actual/display name** is optional. Leave it blank to use TEDUH's registered name, or enter the clearer name your team wants to see.
- **Parent group** is your team's public corporate-group mapping.
- **Project set** can be `reporting_set`, `comparator_set`, or `general`.
- **Launch date**, **built-up range**, and **PSF range** are optional local fields. Launch date remains separate from TEDUH's First SPA date, and blank values stay hidden.
- **Tracking notes** are local and optional.
- **Active** controls whether the project can be refreshed.

Saving a new active TEDUH code immediately retrieves and publishes that project's current public facts. Saving an existing project updates its local fields without making a source request.

Use **Tracked projects** to remove an invalid or no-longer-required project from the master library. Removal also clears the project from saved profiles and the current dashboard, but retains its dated observations and records an audit event.

The **Projects** page always shows the master tracked library. After opening a project's details, use the classification controls to add, reclassify or remove it in the active profile. In the Admin / Master Portfolio, the same control changes the master Reporting, Comparator or General classification; global removal remains under **Tracked projects**.

## Understanding the refresh

A normal refresh makes two public API requests for each uncached active project: project details and unit details. It does not crawl every project in the selected regions.

The output has two kinds of columns:

- **Local shortlist fields:** region, display name, parent group, project set, notes, and active flag.
- **TEDUH/derived fields:** registered project/developer names, status, units, calculated overall and component sales, construction, contractual dates, CCC, values, confidence, permit/licence information, and source URLs.

Manual fields are preserved when TEDUH is refreshed. A source failure cannot silently replace the last valid output.

Use **Refresh this project** in a project detail, or the selector in **Tracked projects**, to update one project without running the full shortlist. The **Compare** page can refresh the active profile's Comparator Set together. These controls request only projects that do not yet have an observation for the current local calendar day. Selected rows are validated and merged without replacing unrelated project data.

The **Refresh & data quality** page retains a refresh-status panel after Streamlit reruns. It records whether the latest attempt succeeded or failed, project counts, elapsed time, same-day cache usage, source data-through date, publication outcome, and recent runs. A failed run explicitly records that the previous valid snapshot was preserved.

## Project details and component sales

The detail page keeps the current overall status, sales, construction, completion and latest movement visible. Less frequently used contractual, component, permit/licensing, local-field, provenance and historical information is placed in collapsible sections.

Sales by component are calculated independently from each `unitGroups[]` collection in TEDUH's unit response. The application never averages component percentages to produce the overall percentage. When TEDUH supplies no friendly block name, the dashboard uses neutral labels such as `Component 1`; it does not infer a tower name from unit-number prefixes.

Nearby comparator analysis displays the selected anchor using the same commercial fields as the candidate rows. Candidate columns prioritise distance, units, potential listed GDV, average unit price and the middle-50% listed price range before monitoring status.

## Understanding Discovery

Discovery is for finding projects that are not yet tracked. It downloads one selected region's catalogue pages, not every project's unit data, and writes a region-specific catalogue such as `data/processed/penang_discovery_catalog.csv`.

- A successful live discovery is capped at once per region per local calendar day.
- Repeating it on the same day reuses the saved catalogue.
- Searching and filtering the saved catalogue does not contact TEDUH.
- A discovered project is not downloaded in detail until it is added to the shortlist. Adding it triggers its first targeted refresh.

This makes discovery broader but occasional, while ordinary monitoring stays small and predictable.

## Alerts

Current-state alerts include:

- `critical`: TEDUH status is `Sakit` or cancelled/abandoned.
- `high`: TEDUH status is `Lewat`.
- `info`: a construction aggregate was withheld because the source rows could not be safely reconciled.

After more than one dated observation, change alerts can also flag status changes, sold-unit decreases, construction decreases, and a new CCC/CFO result. Alerts are review prompts, not automated credit conclusions.

## Scale bands

Potential listed GDV is used only as an indicative screening field:

- Below RM50 million: below the working Commercial Banking floor.
- RM50 million to below RM100 million: include.
- RM100 million to RM500 million: include.
- Above RM500 million: include for Commercial Banking/Large Corp review.
- Missing or low-confidence value: review manually; never automatically exclude.

The calculation is not audited revenue, official developer GDV, nett pricing, or a credit recommendation.

## Source and reuse boundary

The seeded shortlist contains public TEDUH project codes/names and permitted public parent-group mappings only. It excludes CHGP nett pricing, analyst notes, competitor reasoning, and company-specific analysis.

TEDUH remains the source of project facts. Local labels and mappings are visibly separate so an analyst can tell what came from the source and what the team entered.

## If something fails

Read the dashboard error without deleting existing output files. Common causes are a temporary TEDUH outage or network restriction. The last verified current snapshot and history remain intact. Retry later; do not use `--force` repeatedly.
