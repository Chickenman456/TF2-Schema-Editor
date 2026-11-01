@echo off
setlocal
cd /d "%~dp0"

if not exist ".build-venv\Scripts\python.exe" python -m venv .build-venv
if errorlevel 1 exit /b %errorlevel%

".build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b %errorlevel%

".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --name TF2SchemaWorkshop --add-data "web;web" launcher.py
if errorlevel 1 exit /b %errorlevel%

".build-venv\Scripts\python.exe" package_windows.py
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$archive = Join-Path (Get-Location) 'dist\TF2SchemaWorkshop-windows-x64.zip'; if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }; Compress-Archive -Path 'dist\TF2SchemaWorkshop\*' -DestinationPath $archive"
if errorlevel 1 exit /b %errorlevel%

echo Release package created: dist\TF2SchemaWorkshop-windows-x64.zip
