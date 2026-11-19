@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuanian Metal Enterprises (LT_METL_INLT)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LITHUANIAN METAL ENTERPRISES
echo   Input:   LT_METL_INLT_1ENR.csv (Enriched from info.lt)
echo   Output:  LT_METL_INLT_1ENR.csv + LT_METL_INLT_2COL.csv + READY
echo   Method:  Google Maps Match + Official Website Email B2B Crawl
echo   Storage: Incremental Auto-Save + Checkpoint Cache
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

if not exist "LT_METL_INLT_1ENR.csv" (
    if not exist "LT_METL_LTOR_0RAW.csv" (
        echo [ERROR] Neither LT_METL_INLT_1ENR.csv nor LT_METL_LTOR_0RAW.csv found!
        pause
        exit /b 1
    )
)

echo [1/1] Launching Enrichment (Visual Chrome Mode - Headless=False)...
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_metal.py %*

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_METL_INLT_1ENR.csv (Enriched dataset)
echo     - LT_METL_INLT_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo     - LT_METL_INLT_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo     - Synced to csdl_mlt\ and archive\lt_lithuania\
echo =======================================================================
pause
