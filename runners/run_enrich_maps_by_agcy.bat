@echo off
chcp 65001 >nul
title Google Maps Enrichment - Belarus Recruitment Agencies (BY_AGCY)

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - BELARUS RECRUITMENT AGENCIES 2026
echo   Input:   BY_AGCY_PDF0_0RAW.csv (64 Licensed Agencies)
echo   Output:  BY_AGCY_GMAP_1ENR.csv + BY_AGCY_GMAP_2COL.csv + READY
echo   Method:  Cyrillic-Latin Smart Matching + Google Maps + Website Crawl
echo   Storage: Incremental Auto-Save + Checkpoint Cache
echo =======================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

if not exist "BY_AGCY_PDF0_0RAW.csv" (
    echo [ERROR] Target file BY_AGCY_PDF0_0RAW.csv does not exist!
    pause
    exit /b 1
)

echo [1/1] Launching Enrichment (Visual Chrome Mode - Headless=False)...
echo You can observe Chrome searching Google Maps, matching agency names, and extracting B2B emails.
echo.

.venv\Scripts\python.exe crawlmail\enrich_maps_by_agcy.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - BY_AGCY_GMAP_1ENR.csv (Full enriched dataset)
echo     - BY_AGCY_GMAP_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo     - BY_AGCY_GMAP_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo     - Synced to BY_AGCY_PDF0_2COL.csv, csdl_mlt\ and archive\by_belarus\
echo =======================================================================
echo.
pause

