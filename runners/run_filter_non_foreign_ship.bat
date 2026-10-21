@echo off
chcp 65001 >nul
title Filter Non Foreign Hiring Companies
cd /d "%~dp0\.."

echo ======================================================
echo    FILTER NON FOREIGN HIRING COMPANIES
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\filter_non_foreign_ship.py

echo.
echo ======================================================
echo    TASK COMPLETED!
echo ======================================================
pause
