@echo off
REM Launches the Ward-Tordai fitting GUI using the project's virtual environment.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" -m ward_tordai
endlocal
