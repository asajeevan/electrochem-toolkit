@echo off
REM One-time setup: creates the Python environment and installs everything.
cd /d "%~dp0"
echo Creating the Python environment...
py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :fail
echo Installing packages (this takes a few minutes)...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || goto :fail
.venv\Scripts\python.exe -m pip install --quiet -r requirements-native.txt || echo (MPR reader not installed: Git missing? .mpt files still work)
.venv\Scripts\python.exe -m pip install --quiet -r requirements-gui.txt || echo (Desktop app packages not installed: Analyse.bat still works)
.venv\Scripts\python.exe -m pip install --quiet pytest originpro
echo Running the self-tests (about five minutes; each dot is a test that passed)...
.venv\Scripts\python.exe -m pytest -q
echo.
echo Creating Cyclara shortcuts on the Desktop and in the Start menu...
set "CYCLARA_DIR=%CD%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=$env:CYCLARA_DIR; $w=New-Object -ComObject WScript.Shell; foreach ($f in @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) '.'))) { $s=$w.CreateShortcut((Join-Path $f 'Cyclara.lnk')); $s.TargetPath=(Join-Path $d '.venv\Scripts\pythonw.exe'); $s.Arguments='-m electrochem.studio'; $s.WorkingDirectory=$d; $s.IconLocation=(Join-Path $d 'electrochem\studio\assets\cyclara.ico'); $s.Description='Cyclara: EC-Lab cycling analysis'; $s.Save() }" || echo (Shortcuts not created; Cyclara.bat in this folder works the same.)
echo.
echo Setup finished. Open Cyclara from the Desktop or the Start menu,
echo or double-click Cyclara.bat in this folder.
echo (Analyse.bat still opens the simple one-window version.)
pause
exit /b 0
:fail
echo.
echo Setup failed. Is Python 3.12 installed from python.org with "Add to PATH" ticked?
pause
exit /b 1
