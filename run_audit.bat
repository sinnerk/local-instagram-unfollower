@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  set /p "EXPORT=Path to Instagram export ZIP or folder: "
) else (
  set "EXPORT=%~1"
)

if not defined EXPORT (
  echo No export path provided.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.9 or newer and try again.
  pause
  exit /b 1
)

python ig_audit.py "%EXPORT%" --out "%~dp0instagram_audit.html" --open
if errorlevel 1 pause
endlocal
