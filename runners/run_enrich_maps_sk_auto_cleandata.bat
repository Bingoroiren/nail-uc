@echo off
chcp 65001 >nul
title Google Maps Enrichment - Slovakia Auto CleanData
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS DATA ENRICHMENT - SK_AUTO_SLVD CleanData
echo   Target: (xong 10_15) SK_AUTO_SLVD - CleanData.csv
echo   Visual Mode: Headless=False (Chrome Window)
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_maps_sk_auto_cleandata.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT HOAC DA DUOC LUU TANG DAN AN TOAN!
echo   Outputs:
echo   - (xong 10_15) SK_AUTO_SLVD - CleanData.csv (100%% Email len dau)
echo   - SK_AUTO_SLVD_READY_OK.csv (Check gui = OK)
echo =======================================================================
pause
