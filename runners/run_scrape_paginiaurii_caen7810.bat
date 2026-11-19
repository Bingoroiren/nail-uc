@echo off
title Pagini Aurii Scraper - Romanian Employment Agencies CAEN 7810
cd /d "%~dp0\.."

echo =======================================================================
echo   PAGINI AURII ROMANIA SCRAPER - CAEN 7810 EMPLOYMENT AGENCIES
echo   Target : https://www.paginiaurii.ro/firmy/-/q_activitati...cod+caen+7810/
echo   Scope  : 253 pages, ~5,053 Official Romanian Employment Agencies
echo   Outputs: RO_AGCY_PAUR_0RAW.csv, RO_AGCY_PAUR_2COL.csv
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

echo [INFO] Starting scrape_paginiaurii_caen7810.py...
echo.

.venv\Scripts\python.exe -u crawlmail\scrape_paginiaurii_caen7810.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Scraper stopped with errors!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   SCRAPING AND ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Outputs:
echo     - RO_AGCY_PAUR_0RAW.csv (Master raw dataset with CUI, Address, City)
echo     - RO_AGCY_PAUR_2COL.csv (ColdMail 20-col standard, emails sorted first)
echo     - RO_AGCY_PAUR_ONLY_EMAILS_READY.csv (Outreach-ready leads)
echo =======================================================================
pause
