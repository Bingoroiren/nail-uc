@echo off
title Multi-Engine Search and B2B Email Enrichment for Romanian Agencies
cd /d "%~dp0\.."

echo =======================================================================
echo   MULTI-ENGINE OFFICIAL WEBSITE DISCOVERY AND EMAIL ENRICHMENT (RO_AGCY)
echo   Target : RO_AGCY_GMAP_2COL.csv (Romanian Employment Agencies)
echo   Mode   : Visual Browser (headless=False) + curl_cffi Chrome 120
echo   Stages : 1. Google Maps Place Lookup with Strict Name Match
echo            2. Organic Web Search Fallback for Genuine .ro Domains
echo            3. Deep B2B Email Extraction from Official Websites
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

echo [INFO] Starting enrich_search_ro_agcy.py...
echo.

.venv\Scripts\python.exe -u crawlmail\enrich_search_ro_agcy.py %*

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
echo     - RO_AGCY_GMAP_2COL.csv (Master 20-col dataset, emails sorted to top)
echo     - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv (Outreach-ready leads)
echo =======================================================================
pause
