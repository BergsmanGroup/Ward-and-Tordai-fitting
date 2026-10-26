@echo off
REM Builds a standalone Windows executable in dist\WardTordai.exe.
setlocal
cd /d "%~dp0"
python package.py
if errorlevel 1 exit /b 1
endlocal
