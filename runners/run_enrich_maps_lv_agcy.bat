@echo off
chcp 65001 >nul
title Google Maps Enrichment - Latvia Agencies (LV_AGCY_WEBD)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS DATA ENRICHMENT - LATVIA EMPLOYMENT AGENCIES
echo   Dataset: LV_AGCY_WEBD_2COL.csv (Visual Mode - Headless=False)
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_maps_lv_agcy.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT HOAC DA DUOC LUU TANG DAN AN TOAN!
echo   Output:
echo   - LV_AGCY_WEBD_2COL.csv (Thu muc goc - 100%% Email len dau)
echo   - LV_AGCY_WEBD_1ENR.csv
echo =======================================================================
pause
