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

exec ".venv/bin/python" -m streamlit run "src/teduh_monitor/app.py" --server.headless true --server.address 127.0.0.1 --server.port 8501
