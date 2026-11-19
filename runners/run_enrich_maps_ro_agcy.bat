@echo off
title Google Maps Enrichment - Romanian Employment Agencies (RO_AGCY_GMAP)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - ROMANIAN EMPLOYMENT AGENCIES (RO_AGCY)
echo   Input  : RO_AGCY_DIR0_1ENR.csv (Active agencies without Email/Phone)
echo   Output : RO_AGCY_GMAP_1ENR.csv + RO_AGCY_GMAP_2COL.csv
echo            RO_AGCY_GMAP_ONLY_EMAILS_READY.csv + ro_romania\
echo   Method : Strict RO Name Match + Visual Chrome + JS/HTTP Email Crawl
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

if not exist "RO_AGCY_DIR0_1ENR.csv" (
    if not exist "ro_romania\RO_AGCY_DIR0_1ENR.csv" (
        echo [ERROR] RO_AGCY_DIR0_1ENR.csv not found!
        pause
        exit /b 1
    )
)

echo [1/2] Checking core Python dependencies...
".venv\Scripts\python.exe" -c "import playwright, curl_cffi, bs4, pandas" 2>nul
if errorlevel 1 (
    echo [*] Installing missing packages into .venv...
    ".venv\Scripts\pip.exe" install playwright curl_cffi beautifulsoup4 pandas
)

echo [2/2] Launching Google Maps Enrichment (Visual Chrome - headless=False)...
echo Checkpoints are saved after each company (JSON) and every 5 companies (CSV).
echo.
".venv\Scripts\python.exe" crawlmail\enrich_maps_ro_agcy.py %*

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR SAVED AT CHECKPOINT
echo   Outputs saved:
echo     - RO_AGCY_GMAP_1ENR.csv
echo     - RO_AGCY_GMAP_2COL.csv
echo     - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv
echo     - ro_romania\RO_AGCY_GMAP_1ENR.csv and RO_AGCY_GMAP_2COL.csv
echo =======================================================================
pause

