@echo off
title Romanian Directory Enrichment - ANAF and CompanyWall and PaginiAurii (RO_AGCY)
cd /d "%~dp0\.."

echo =======================================================================
echo   ROMANIAN DIRECTORY ENRICHMENT - RO EMPLOYMENT AGENCIES (RO_AGCY)
echo   Input  : ro_romania\RO_AGCY_COMPANIES_CUI.csv (892 companies)
echo   Sources: ANAF API v9 + CompanyWall.ro + PaginiAurii.ro + Web Crawl
echo   Output : RO_AGCY_DIR0_1ENR.csv + RO_AGCY_DIR0_2COL.csv
echo            RO_AGCY_DIR0_ONLY_EMAILS_READY.csv + ro_romania\
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

if not exist "ro_romania\RO_AGCY_COMPANIES_CUI.csv" (
    echo [ERROR] ro_romania\RO_AGCY_COMPANIES_CUI.csv not found!
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import curl_cffi, bs4, pandas" 2>nul
if errorlevel 1 (
    echo [*] Installing curl_cffi, beautifulsoup4, pandas into .venv...
    ".venv\Scripts\pip.exe" install curl_cffi beautifulsoup4 pandas
)

".venv\Scripts\python.exe" crawlmail\enrich_ro_directories.py %*

echo.
echo =======================================================================
echo   DIRECTORY ENRICHMENT COMPLETED OR SAVED AT CHECKPOINT
echo =======================================================================
pause

