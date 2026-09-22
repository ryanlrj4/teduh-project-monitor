#!/bin/bash

set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "The Mac Python environment has not been prepared yet."
  echo "Follow the installation steps in README.md, then run this launcher again."
  echo
  read -r -p "Press Return to close this window."
  exit 1
fi

exec ".venv/bin/python" -m streamlit run "src/teduh_monitor/app.py" --server.headless true --server.address 127.0.0.1 --server.port 8501
