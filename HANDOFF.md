# Mac handover: TEDUH Regional Project Monitor

## For the user

This folder is the complete working project. It includes the application, the
editable shortlist, today's current dashboard snapshot, alerts, and the opening
dated history. Windows-only Python files and temporary research downloads are
deliberately excluded from GitHub.

After cloning this private repository onto the Mac, open the cloned folder in
Codex and send this message:

> Read HANDOFF.md. Set up this project for macOS, run its tests, and launch the Streamlit dashboard locally. Do not refresh TEDUH unless I ask.

Once Codex finishes the one-time setup, `run_dashboard.command` can be used to
start the dashboard again. If macOS does not initially allow it to open, ask
Codex to make the launcher executable.

## For Codex on the Mac

The user is a coding beginner. Perform the setup rather than only explaining
shell commands. Work from the cloned repository and preserve all existing CSV
state.

1. Confirm that Python 3.11 or newer is available. Prefer Python 3.12 when more
   than one suitable version is installed.
2. Create a new macOS virtual environment at `.venv`; never reuse or copy the
   Windows environment.
3. Install the project with its development dependencies:
   `python -m pip install -e ".[dev]"`.
4. Run `python -m pytest -q` and report the result.
5. Make `run_dashboard.command` executable if required.
6. Start the dashboard through `run_dashboard.command` or the equivalent
   `.venv/bin/python -m streamlit run src/teduh_monitor/app.py` command.
7. Confirm that `http://localhost:8501` loads.
8. Do not run Discovery or contact TEDUH during setup unless the user explicitly
   requests fresh data. The checked-in CSV snapshot should make the dashboard
   immediately useful offline.

## Current functional state

- Supported regions: Kuala Lumpur and Penang.
- Active shortlist: 50 projects.
- Sets: Reporting Set, Comparator Set, and General.
- RM-first navigation: My Portfolio, Groups, Compare, Projects and Alerts, with
  maintenance functions grouped separately.
- Portfolio profiles reuse one underlying TEDUH dataset. The Admin / Master
  Portfolio retains all tracked projects and a small Test Portfolio is included.
- Current details distinguish TEDUH, local, calculated and application-generated
  fields. They include unit and value sales, remaining inventory/quota detail,
  price realisation, overall and component sales, contractual VP changes,
  component construction, permit/developer licensing, CCC/CFO, retrieval timing,
  and visible weekly history in a compact hierarchy.
- The Refresh & data quality page persists the latest refresh outcome and recent run history.
- Pinnacle Bukit Gambier has a locally entered built-up range of
  `1,080–1,726 sqft`.
- Run the complete automated suite after setup. The checked-in data contains
  50 current projects and dated observations for offline dashboard use.

## Files that must remain preserved

- `config/shortlist.csv`: editable shortlist and local fields.
- `data/processed/shortlist_current.csv`: current dashboard snapshot.
- `data/processed/shortlist_alerts.csv`: current alerts.
- `data/history/shortlist_history.csv`: dated observations used for trends.

The ignored raw downloads, Parquet files, optional legacy KL proof outputs,
virtual environment, and temporary PDFs can all be regenerated. They are not
required to open the current dashboard.

## Privacy boundary

The repository must remain private. It contains public TEDUH information and
local display-name/parent-group mappings, but no customer-confidential banking
information should be added. Do not add facility details, credit decisions,
internal pricing, or restricted bank information to notes.

## Normal two-computer routine

Before beginning work, pull the newest GitHub changes. Before changing computers,
commit the finished work and push it to GitHub. Avoid editing the project on both
computers at the same time.
