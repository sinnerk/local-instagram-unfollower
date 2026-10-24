@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0gui.py" %*
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw "%~dp0gui.py" %*
    exit /b 0
)

python "%~dp0gui.py" %*
if errorlevel 1 (
    echo.
    echo Python was not found. Install Python 3.9 or newer from python.org
    echo and tick "Add Python to PATH" during setup.
    pause
)
