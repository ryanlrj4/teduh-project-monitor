@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Please run the installation steps in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run "src\teduh_phase2\app.py"
