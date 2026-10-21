@echo off
chcp 65001 >nul
title Crawl Seanet Job List and Update 0RAW
cd /d "%~dp0\.."

echo ======================================================
echo    CRAWL SEANET JOB LIST AND UPDATE KR_SHIP_DSTU_0RAW
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\crawl_kr_seanet.py

echo.
echo ======================================================
echo    TASK COMPLETED!
echo ======================================================
pause
