@echo off
REM Opens Cyclara. Run Setup.bat once before the first use.
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Run Setup.bat first: double-click it in this folder and wait until it says "Setup finished".
  pause
  exit /b 1
)
.venv\Scripts\python.exe -c "import PySide6, pyqtgraph" 2>nul || (
  echo Cyclara's packages are missing. Double-click Setup.bat again, then try once more.
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe -m electrochem.studio %*
