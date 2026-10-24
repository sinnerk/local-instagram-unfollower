@echo off
title Local Instagram Unfollower
cd /d "%~dp0"
python gui.py
if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed.
    pause
)
