@echo off
title Google Maps Enrichment - Lithuanian Warehousing and Transport Support (LT_WARE)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LT WAREHOUSING AND TRANSPORT (LT_WARE)
echo   Input:   LT_WARE_INLT_2COL.csv + LT_WARE_INLT_1ENR.csv
echo   Output:  LT_WARE_GMAP_1ENR.csv + LT_WARE_GMAP_2COL.csv
echo            LT_WARE_GMAP_ONLY_EMAILS_READY.csv + Sync LT_WARE_INLT_2COL.csv
echo   Method:  Strict Name Match + Visual Chrome + Multi-Tier Email Crawl
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

if not exist "LT_WARE_INLT_2COL.csv" (
    echo [ERROR] LT_WARE_INLT_2COL.csv not found in workspace root!
    pause
    exit /b 1
)

echo [1/2] Checking core Python dependencies...
".venv\Scripts\python.exe" -c "import playwright, curl_cffi, bs4, pandas" 2>nul
if errorlevel 1 (
    echo [*] Installing missing packages into .venv...
    ".venv\Scripts\pip.exe" install playwright curl_cffi beautifulsoup4 pandas
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - headless=False)...
echo Checkpoints are saved after each company (JSON) and every 5 companies (CSV).
echo.
".venv\Scripts\python.exe" crawlmail\enrich_maps_lt_ware.py %*

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Outputs saved and synced:
echo     - LT_WARE_GMAP_1ENR.csv
echo     - LT_WARE_GMAP_2COL.csv
echo     - LT_WARE_GMAP_ONLY_EMAILS_READY.csv
echo     - LT_WARE_INLT_2COL.csv
echo     - csdl_mlt\ + archive\lt_lithuania\
echo =======================================================================
pause

