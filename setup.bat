@echo off
REM Creates a virtual environment and installs the ward_tordai package + dependencies.
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
)

echo Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo Installing ward-tordai-fit and dependencies ...
".venv\Scripts\python.exe" -m pip install -e ".[test]"

echo.
echo Setup complete. Use run.bat to launch the application.
endlocal
