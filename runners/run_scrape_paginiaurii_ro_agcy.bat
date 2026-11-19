@echo off
chcp 65001 >nul
title Scraper Pagini Aurii Romania and Supplement RO_AGCY_GMAP_2COL
cd /d "%~dp0\.."

echo =======================================================================
echo   SCRAPE PAGINI AURII RO AND SUPPLEMENT RO_AGCY_GMAP_2COL.CSV
echo   Target: https://www.paginiaurii.ro/firmy/-/q_recrutare+si+plasare...
echo   Mode  : Scrape 15 pages + Deep Contacts + Match and Enrich
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [INFO] Running scrape_paginiaurii_ro_agcy.py...
echo.

.venv\Scripts\python.exe crawlmail\scrape_paginiaurii_ro_agcy.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   SCRAPING AND SUPPLEMENTING COMPLETED SUCCESSFULLY!
echo   Outputs:
echo     - RO_AGCY_GMAP_2COL.csv (Master 20-col dataset, enriched and updated)
echo     - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv (Outreach-ready rows)
echo     - RO_AGCY_PAUR_0RAW.csv (Pagini Aurii standalone raw data)
echo     - RO_AGCY_PAUR_2COL.csv (Pagini Aurii standalone 20-col Cold Mail)
echo =======================================================================
pause
