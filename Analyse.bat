@echo off
REM Opens the analysis window. Run Setup.bat once before the first use.
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Run Setup.bat first.
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe -m electrochem.gui
