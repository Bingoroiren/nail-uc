@echo off
title CAPTCHA-Free B2B Email Enrichment for Romanian Agencies (PAUR)
cd /d "%~dp0\.."

echo =======================================================================
echo   CAPTCHA-FREE B2B EMAIL ENRICHMENT - ROMANIAN EMPLOYMENT AGENCIES
echo   Target : RO_AGCY_PAUR_2COL.csv (3,805 CAEN 7810 Employment Agencies)
echo   Engines: CompanyWall (by CUI) + DuckDuckGo (site:ro) + curl_cffi
echo   Advantage: NO Google Captcha, Fast HTTP Multi-Tier B2B Email Extraction
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

echo [INFO] Starting enrich_nocaptcha_ro_agcy.py...
echo.

.venv\Scripts\python.exe -u crawlmail\enrich_nocaptcha_ro_agcy.py %*

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
