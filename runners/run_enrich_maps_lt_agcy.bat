@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuania Agencies (LT_AGCY_REKV)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS DATA ENRICHMENT - LITHUANIA EMPLOYMENT AGENCIES
echo   Dataset: LT_AGCY_REKV_2COL.csv (Visual Mode - Headless=False)
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\enrich_maps_lt_agcy.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT HOAC DA DUOC LUU TANG DAN AN TOAN!
echo   Output:
echo   - LT_AGCY_REKV_2COL.csv (Thu muc goc - 100%% Email len dau)
echo   - csdl_mlt\LT_AGCY_REKV_2COL.csv
echo   - csdl_mlt\LT_AGCY_REKV_1ENR.csv
echo =======================================================================
pause
