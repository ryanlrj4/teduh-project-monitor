# Phase 3 Operating Guide

## What Phase 3 does

Phase 3 changes the proof into a focused local monitor:

1. Start with the authorized Kuala Lumpur comparison set and selected reporting-set projects in other regions.
2. Refresh only projects marked active.
3. Save one observation per project per local calendar day.
4. Show current metrics, dated history, and risk alerts.
5. Let the user add or edit projects without changing Python code.

The shortlist can be refreshed manually. The `refresh-if-due` command is intended for a Monday scheduler and makes no request if the current week already has a successful observation.

## Adding or editing a project

Open **Add or edit** in the dashboard.

- **TEDUH project code** is the public stable key, for example `30031-1`.
- **Region** is a controlled selection used to verify TEDUH's state and filter the dashboard.
- **Actual/display name** is optional. Leave it blank to use TEDUH's registered name, or enter the clearer name your team wants to see.
- **Parent group** is your team's public corporate-group mapping.
- **Project set** can be `reporting_set`, `comparator_set`, or `general`.
- **Launch date**, **built-up range**, and **PSF range** are optional local fields. Launch date remains separate from TEDUH's First SPA date, and blank values stay hidden.
- **Priority** can be `high`, `medium`, or `low`.
- **Tracking notes** are local and optional.
- **Active** controls whether the project is included in the next shortlist refresh.

Saving an existing TEDUH code updates that row. The next successful refresh combines those local fields with current public TEDUH facts.

## Understanding the refresh

A normal refresh makes two public API requests for each uncached active project: project details and unit details. It does not crawl every project in the selected regions.

The output has two kinds of columns:

- **Local shortlist fields:** region, display name, parent group, project set, priority, notes, and active flag.
- **TEDUH/derived fields:** registered project/developer names, status, units, calculated sales, construction, CCC, values, confidence, dates, and source URLs.

Manual fields are preserved when TEDUH is refreshed. A source failure cannot silently replace the last valid output.

## Understanding Discovery

Discovery is for finding projects that are not yet tracked. It downloads one selected region's catalogue pages, not every project's unit data, and writes a region-specific catalogue such as `data/processed/penang_discovery_catalog.csv`.

- A successful live discovery is capped at once per region per local calendar day.
- Repeating it on the same day reuses the saved catalogue.
- Searching and filtering the saved catalogue does not contact TEDUH.
- A discovered project is not downloaded in detail until it is added to the shortlist and a shortlist refresh is run.

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
