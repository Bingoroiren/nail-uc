@echo off
title Google Maps and Web B2B Email Enrichment for Romanian Agencies (PAUR)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS AND B2B EMAIL ENRICHMENT - ROMANIAN AGENCIES (PAUR)
echo   Target : RO_AGCY_PAUR_2COL.csv (3,805 CAEN 7810 Employment Agencies)
echo   Mode   : Visual Browser (headless=False) + curl_cffi Chrome 120
echo   Stages : 1. Google Maps Place Lookup with Strict Name Match
echo            2. Category Guard (Reject Non-Agency businesses)
echo            3. Organic Web Search Fallback for Genuine .ro Domains
echo            4. Deep B2B Email Extraction from Official Websites
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

echo [INFO] Starting enrich_maps_ro_paur.py...
echo.

.venv\Scripts\python.exe -u crawlmail\enrich_maps_ro_paur.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script stopped with errors!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Outputs:
echo     - RO_AGCY_PAUR_2COL.csv (Master 20-col dataset, emails sorted to top)
echo     - RO_AGCY_PAUR_ONLY_EMAILS_READY.csv (Outreach-ready leads)
echo =======================================================================
pause
