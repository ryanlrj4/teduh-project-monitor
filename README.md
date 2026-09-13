# TEDUH Regional Project Monitor

This is a local, beginner-friendly monitoring dashboard for selected private-housing projects across supported Malaysian regions. It reads the public TEDUH JSON API, keeps dated observations, and highlights sales, construction, and status risks without requiring a database server or cloud account.

The shortlist contains the authorized Kuala Lumpur comparison set and user-selected tracked projects in the supported regions. It contains only public TEDUH identifiers/facts and permitted local mappings. It does **not** contain bank financing information, CHGP pricing, analyst notes, comparison reasoning, or other proprietary analysis.

## Start the dashboard

Double-click `run_dashboard.bat`.

The dashboard opens locally in your browser. Its sidebar is organised around the RM workflow:

- **My Portfolio** — attention items, recent movements and the active profile's Reporting Set.
- **Groups** — search and roll up developments mapped to the same parent group or registered developer.
- **Compare** — find nearby candidates, add them to a comparison or Comparator Set, and compare up to six projects.
- **Projects** — search and filter the full tracked-project library.
- **Alerts** — review business-facing status, permit, developer, commercial-progress and data-quality exceptions.
- **Manage** — maintain profiles, tracked projects, Discovery, refresh/data quality and the audit log.

Portfolio profiles are saved working views, not security roles. The Admin / Master Portfolio uses the full tracked-project register; a small Test Portfolio demonstrates a separate project selection and classification without duplicating TEDUH observations.

The dashboard supports both full and targeted refreshes. A newly added active project is fetched immediately; project details and Tracked projects can refresh one stale project; and Compare can refresh stale Comparator Set projects. A project with an observation from the current local calendar day is skipped. `run_weekly_refresh.bat` is the safe Monday-oriented scheduler command: it refreshes only when the current Monday-based week has no successful observation. Registering the command with Windows Task Scheduler is a deployment step; the computer must be on and connected when it runs.

## What is tracked

- Regions: `Kuala Lumpur` (`state=14`) and `Penang` (`state=07`)
- HIMS eligibility cutoff: `2022-01-31`
- Active statuses: `Belum Mula`, `Lancar`, `Sakit`, `Lewat`
- Completed statuses: `Siap Dengan CCC`, `Siap Dengan CFO`
- Normal refresh: active projects in `config/shortlist.csv` only
- Discovery: catalogue metadata only; no unit-level downloads until a project is added and refreshed

Legacy projects are excluded when their first SPA date, or permit start fallback, predates the HIMS cutoff. This prevents partial post-2022 rows from being presented as a complete project history.

CCC/CFO obtained remains a Yes/No field. `Yes` is supported by a completed-with-CCC/CFO project status or explicit component evidence. When TEDUH supplies component dates, the project details also show the latest valid CCC/CFO date and VP date separately.

Project details distinguish TEDUH facts, locally maintained fields, application-generated timestamps, and deterministic calculations. The first view prioritises unit and value sales, construction, typical listed unit pricing, recorded SPA pricing, latest movement and weekly trends. Additional sections show remaining inventory by type/quota, recorded price realisation, contractual VP changes, component construction, permit/developer licensing, and sales calculated separately for each TEDUH unit group. Neutral component labels are used when TEDUH does not provide a block name. Actual VP remains available in the contractual detail but is not a headline measure unless an exception requires attention.

Typical unit price uses the median valid TEDUH listed price, with the middle 50% shown as the typical range. High- and low-priced units remain in total listed GDV; they are not silently removed. Price-distribution and recorded-SPA unit metrics require a refresh created with transformation version 1.5.1.

## First-time installation

Python 3.11 or newer is required. In PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
```

No passwords, API keys, `.env` file, Supabase, or PostgreSQL are required.

## First-time installation on macOS

The easiest route for a beginner is to open the cloned project folder in Codex and ask it to read `HANDOFF.md`, set up the project for macOS, run the tests, and launch the dashboard. Codex should create a fresh Mac `.venv`; the Windows environment is intentionally not transferred.

After that one-time setup, double-click `run_dashboard.command` to start the local dashboard. The Mac runs its own `http://localhost:8501`; the Windows localhost process is not transferred through GitHub.

## Useful commands

```powershell
# Refresh only the active shortlist
.venv\Scripts\python -m teduh_monitor.cli refresh

# Safe command for a weekly scheduler; does nothing when this week is already current
.venv\Scripts\python -m teduh_monitor.cli refresh-if-due

# Build/reuse a once-daily regional discovery catalogue
.venv\Scripts\python -m teduh_monitor.cli discover --region "Penang"

# Verify the current shortlist and history outputs
.venv\Scripts\python -m teduh_monitor.cli validate-monitor

# Run fixed tests without accessing TEDUH
.venv\Scripts\python -m pytest
```

The older KL full-universe data proof is quarantined behind the explicit
`legacy-kl-full-catalog` and `legacy-kl-validate` commands. Neither command is
part of normal monitoring.

## Main files

- Editable shortlist: `config/shortlist.csv`
- Current CSV: `data/processed/shortlist_current.csv`
- Current Parquet: `data/processed/shortlist_current.parquet`
- Dated history: `data/history/shortlist_history.csv` and `.parquet`
- Alerts: `data/processed/shortlist_alerts.csv`
- Latest refresh status and recent-run history: ignored local JSON files in `data/processed/`
- Project-change audit log: `data/audit/project_changes.csv` (created on the first new addition or edit)
- Operating guide: `docs/OPERATING_GUIDE.md`
- Modernisation technical pitch: `docs/MODERNISATION_TECHNICAL_PITCH.md`

## Safety behavior

A full refresh verifies every active project before replacing the previous valid files. A targeted refresh validates the requested projects and merges only those rows into the current snapshot and history. HTML/error pages, missing required fields, invalid project codes, state/region mismatches, pre-HIMS projects, and incomplete refreshes stop publication rather than turning missing facts into zeroes. Unrelated projects and the previous valid data remain intact after a targeted failure. The dashboard retains the last full run's status after rerun and explicitly states when a failed full attempt preserved the previous valid snapshot.

The tool is a local analytical aid, not a system of record. Keep customer-confidential information, facility balances, credit decisions, and other bank-restricted data outside its free-text notes unless the environment has been approved for that information.
