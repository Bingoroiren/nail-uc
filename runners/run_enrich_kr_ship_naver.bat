@echo off
chcp 65001 >nul
title Full Batch Enrich Korean Shipping Companies via Naver and Deep Web
cd /d "%~dp0\.."

echo ======================================================
echo    FULL BATCH: ENRICH KOREAN SHIPPING DATA VIA NAVER
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_kr_ship_naver.py

echo.
echo ======================================================
echo    ENRICHMENT TASK COMPLETED!
echo    - KR_SHIP_NAVR_1ENR.csv
echo    - KR_SHIP_NAVR_2COL.csv
echo ======================================================
pause
