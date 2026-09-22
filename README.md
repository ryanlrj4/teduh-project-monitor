# TEDUH Project Monitor

Working proof of concept for monitoring selected Malaysian private-housing projects using the public JSON endpoints behind KPKT's TEDUH portal.

The application maintains a controlled project register, retrieves current TEDUH project and unit data, calculates monitoring metrics, preserves dated observations, generates deterministic alerts and presents the results through Streamlit.

## Status and scope

- Local, file-backed proof of concept; not a production service or system of record.
- Python 3.11+ and Streamlit.
- Supported regions: Kuala Lumpur, Penang, Selangor, Johor and Malacca (`Melaka` in TEDUH).
- HIMS unit-data eligibility boundary: `2022-01-01`.
- Current transformation version: `1.5.2`.
- No runtime AI dependency. Retrieval, validation, calculations and alerts are deterministic.
- No customer, facility, financing, collateral, credit-decision or internal risk data is required.

The repository contains public TEDUH facts plus locally maintained project names, parent-group mappings, project classifications, portfolio membership and audit identities. Those local fields may still require internal handling controls.

## Source endpoints

The client uses the JSON endpoints consumed by the public TEDUH frontend:

```text
GET https://teduh.kpkt.gov.my/api/projek-swasta
GET https://teduh.kpkt.gov.my/api/projek-swasta/{project_code}
GET https://teduh.kpkt.gov.my/api/unit-projek-swasta/{project_code}
GET https://teduh.kpkt.gov.my/api/negeri
GET https://teduh.kpkt.gov.my/api/daerah-by-negeri
GET https://teduh.kpkt.gov.my/api/bandar-by-daerah
```

The search endpoint is paginated and filtered by state and project status. Project detail and unit endpoints use TEDUH's stable project code, for example `20209-1`.

There is no credential or API key. The client performs sequential GET requests with a default 1.1-second minimum interval, a 60-second timeout and three retry attempts. HTTP errors, rate limits, HTML responses and missing expected JSON keys are treated as source failures.

## Data flow

```text
TEDUH JSON endpoints
        │
        ▼
Rate-limited client and dated raw cache
        │
        ▼
Normalization and deterministic metric calculation
        │
        ▼
Schema, coverage and consistency validation
        │
        ▼
Atomic publication of current snapshot, history and alerts
        │
        ▼
Streamlit monitoring interface
```

### Full refresh

1. Load active projects from `config/shortlist.csv`.
2. Retrieve project detail and unit data for every active project.
3. Validate region, HIMS eligibility, response structure and required fields.
4. Calculate sales, value, pricing, construction, completion and coverage metrics.
5. Validate the complete staged result.
6. Atomically replace the current snapshot only after all active projects succeed.
7. Merge one observation per project/date into history and rebuild alerts.

A failed full refresh does not replace the previous valid snapshot.

### Targeted refresh

Targeted refreshes retrieve only selected active projects and merge validated rows into the existing snapshot. Unrelated rows remain unchanged. A project already observed on the current local calendar date is skipped.

### Discovery

Discovery downloads catalogue metadata for one region and caches it for the day. It does not retrieve unit-level data until a project is added to the tracked register. Discovery is separate from the normal monitoring refresh.

## Calculated outputs

The main deterministic outputs include:

- sold, unsold and total units;
- unit-sales percentage;
- estimated value sold and value-sold percentage;
- potential listed GDV and remaining listed value;
- median and average listed price per unit;
- listed-price interquartile range;
- recorded SPA value and price-realisation measures;
- construction percentage and confidence;
- CCC/CFO flag and available completion dates;
- component/block-level sales;
- remaining inventory by component and quota category;
- sales-versus-construction gap;
- dated changes and weekly trends.

Metric definitions and null-handling rules are documented in [`docs/METRIC_DEFINITIONS.md`](docs/METRIC_DEFINITIONS.md). Field-level lineage is documented in [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).

## Application functions

- **My Portfolio:** Reporting Set summary, exceptions and latest movements.
- **Groups:** aggregate projects by locally mapped parent group or TEDUH registered developer.
- **Compare:** anchor-project benchmarks, nearby candidates and multi-project comparison.
- **Projects:** searchable master tracked-project library and detailed project view.
- **Alerts:** deterministic status, permit, developer, progress and data-quality exceptions.
- **Profiles:** saved project selections and classifications over the shared TEDUH dataset.
- **Tracked projects:** master register, targeted refresh and project removal.
- **Add or edit:** controlled local metadata plus automatic TEDUH region detection.
- **Discovery:** on-demand regional catalogue scan.
- **Refresh and data quality:** full refresh execution, progress and recent-run status.
- **Audit log:** additions, removals and local field changes.

Profiles are working views, not authorization boundaries. The Admin / Master Portfolio represents the complete tracked library.

## Repository structure

```text
src/teduh_monitor/
  app.py               Streamlit entry point and page routing
  sources.py           TEDUH HTTP client, caching and source validation
  collection.py        Per-project collection workflow
  normalize.py         Text, date, price, state and status normalization
  metrics.py           Deterministic project and unit calculations
  validate.py          Published-record validation
  monitor.py           Full/targeted refresh, publication, history and alerts
  discovery.py         Regional catalogue discovery
  shortlist.py         Tracked-project register and audit events
  portfolios.py        Profile definitions and project membership
  refresh_status.py    Refresh-run state and recent-run history
  schedule.py          Monday-based refresh-due check
  storage.py           Atomic CSV, JSON and Parquet writes
  schema.py            Output field definitions
  ui/                   Streamlit pages, components, formatting and styles

config/
  shortlist.csv         Master tracked-project register and local metadata
  portfolios.csv        Profile definitions
  portfolio_projects.csv
                        Profile membership and per-profile classification

data/
  raw/                  Dated API response cache; ignored by Git
  processed/            Current snapshot, alerts and local refresh state
  history/              Append/merge dated observations
  audit/                Local project-change audit log
```

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
```

Runtime dependencies are declared in `pyproject.toml`: Streamlit, HTTPX and DuckDB. Pytest is the only development dependency.

## Run locally

macOS/Linux:

```bash
.venv/bin/python -m streamlit run src/teduh_monitor/app.py
```

Windows:

```powershell
.venv\Scripts\python -m streamlit run src/teduh_monitor/app.py
```

Convenience launchers are also provided:

- `run_dashboard.command` for macOS;
- `run_dashboard.bat` for Windows.

The default local address is `http://localhost:8501`.

## Operational commands

The examples below use the POSIX interpreter path. Replace `.venv/bin/python` with `.venv\Scripts\python` on Windows.

```bash
# Full active-register refresh
.venv/bin/python -m teduh_monitor.cli refresh

# Refresh only when the current Monday-based week has no observation
.venv/bin/python -m teduh_monitor.cli refresh-if-due

# Build or reuse a same-day regional discovery catalogue
.venv/bin/python -m teduh_monitor.cli discover --region "Selangor"

# Validate current CSV/Parquet alignment, active-project coverage and history keys
.venv/bin/python -m teduh_monitor.cli validate-monitor

# Run the automated suite without calling TEDUH
.venv/bin/python -m pytest
```

`run_weekly_refresh.bat` wraps `refresh-if-due` for Windows Task Scheduler. Scheduling is external to the application.

## Persisted state

| Path | Purpose | Git policy |
|---|---|---|
| `config/shortlist.csv` | Master project register and local fields | Tracked |
| `config/portfolios.csv` | Profile definitions | Tracked |
| `config/portfolio_projects.csv` | Profile memberships/classifications | Tracked |
| `data/processed/shortlist_current.csv` | Current published snapshot | Tracked |
| `data/processed/shortlist_current.parquet` | Current typed analytical copy | Regenerable, ignored |
| `data/history/shortlist_history.csv` | Dated observations | Tracked |
| `data/history/shortlist_history.parquet` | Typed history copy | Regenerable, ignored |
| `data/processed/shortlist_alerts.csv` | Current deterministic alerts | Tracked |
| `data/audit/project_changes.csv` | Local metadata audit events | Tracked |
| `data/raw/teduh/{date}/` | Raw JSON and request metadata | Regenerable, ignored |
| `data/processed/refresh_status.json` | Latest local refresh status | Local, ignored |
| `data/processed/refresh_runs.json` | Recent local refresh history | Local, ignored |

CSV files use UTF-8 with BOM for compatibility with common Windows tooling. Parquet outputs are generated with DuckDB.

## Validation and failure controls

- Expected JSON content type and top-level keys are checked before processing.
- Project state must match the configured region.
- Projects before the HIMS boundary are not published as comparable unit datasets.
- Unit counts, sales-status vocabulary, percentages, duplicate identifiers and coverage are validated.
- Missing values remain null; source failure is not converted to zero.
- Full publication is all-or-nothing.
- Targeted publication replaces only successfully validated selected projects.
- Writes use temporary files and atomic replacement.
- History is unique on `(snapshot_date, source_project_id)`.
- Retrieval timestamp and TEDUH displayed data-through date are stored separately.
- Raw responses and request metadata are cached by observation date.

Run `validate-monitor` after any manual data-file change and before release or deployment.

## Productionisation requirements

The current implementation is intentionally optimized for a local proof of concept. An internal multi-user deployment should replace or formalize the following:

1. **Identity and authorization** — Microsoft Entra ID/approved SSO, role-based access and server-derived audit identity.
2. **Persistent storage** — approved relational database for configuration, observations, profiles and audit events; object storage for retained raw responses if required.
3. **Job execution** — centrally managed scheduler or worker independent of the Streamlit process.
4. **Concurrency** — transactional writes and locking for simultaneous users and refresh jobs.
5. **Hosting** — approved application/container platform, network egress policy and TLS termination.
6. **Observability** — centralized logs, metrics, job alerts, failure notifications and retention policy.
7. **Source governance** — confirmation of acceptable automated use, request limits, ownership and response-schema change management for TEDUH.
8. **Data governance** — classification of local project mappings, profile membership, user identity and audit history.
9. **Operational ownership** — named product owner, technical owner, support process, deployment pipeline and recovery procedure.
10. **User interface** — retain or rebuild Streamlit according to the approved internal platform and accessibility standards.

The existing Python code can be treated as a reference implementation for the TEDUH connector, business rules, validation controls, calculations and acceptance tests even if the production UI or persistence layer is replaced.

## Known limitations

- File-backed state is suitable for one local writer, not concurrent multi-user operation.
- Profile selection is not access control.
- Audit identity is user-entered in the proof of concept.
- Refresh availability depends on the public TEDUH service and its undocumented internal JSON contract.
- The application has no source SLA and must be maintained if TEDUH changes its schema or endpoints.
- `source_dataset_as_of` follows TEDUH's frontend display convention and is not a transaction timestamp for every unit row.
- Historical trends begin when this application first records a project; the system does not reconstruct earlier TEDUH states.
- Parent-group mappings and project classifications are locally maintained.

## Supporting documentation

- [`docs/OPERATING_GUIDE.md`](docs/OPERATING_GUIDE.md) — user and operator workflow.
- [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) — field definitions and provenance.
- [`docs/METRIC_DEFINITIONS.md`](docs/METRIC_DEFINITIONS.md) — calculation logic.
- [`docs/SOURCE_AUDIT.md`](docs/SOURCE_AUDIT.md) — endpoint and source-quality analysis.
- [`docs/DESIGN_REFERENCE.md`](docs/DESIGN_REFERENCE.md) — interface tokens and styling rationale.
- [`docs/MODERNISATION_TECHNICAL_PITCH.md`](docs/MODERNISATION_TECHNICAL_PITCH.md) — initial enterprise implementation considerations.
