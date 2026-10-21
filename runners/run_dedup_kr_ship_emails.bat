@echo off
chcp 65001 >nul
title Deduplicate Emails for KR SHIP DSTU
cd /d "%~dp0\.."

echo ======================================================
echo    DEDUPLICATE EMAILS IN KR_SHIP_DSTU_0RAW.CSV
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\dedup_kr_ship_emails.py

echo.
echo ======================================================
echo    TASK COMPLETED!
echo ======================================================
pause
