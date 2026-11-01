@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m schema_workshop.server %*
) else (
  python -m schema_workshop.server %*
)
if errorlevel 1 pause
