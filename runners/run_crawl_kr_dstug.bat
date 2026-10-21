@echo off
chcp 65001 >nul
title Crawl DSTUG Marine Companies (Tau To and Tau Dat)
cd /d "%~dp0\.."

echo ======================================================
echo    CRAWL DSTUG.ORG (SHIPPING AGENT AND TUGBOAT)
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\crawl_kr_dstug.py

echo.
echo ======================================================
echo    TASK COMPLETED!
echo ======================================================
pause
