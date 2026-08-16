#!/bin/bash

set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "The Mac Python environment has not been prepared yet."
  echo "Open this folder in Codex and ask it to read HANDOFF.md and complete the Mac setup."
  echo
  read -r -p "Press Return to close this window."
  exit 1
fi

exec ".venv/bin/python" -m streamlit run "src/teduh_phase2/app.py" --server.headless true --server.port 8501
