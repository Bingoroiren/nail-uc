@echo off
chcp 65001 >nul
title Crawl Maritimepress and Update DSTUG 0RAW
cd /d "%~dp0\.."

echo ======================================================
echo    CRAWL MARITIMEPRESS AND UPDATE KR_SHIP_DSTU_0RAW.CSV
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\crawl_kr_maritime.py

echo.
echo ======================================================
echo    TASK COMPLETED!
echo ======================================================
pause
