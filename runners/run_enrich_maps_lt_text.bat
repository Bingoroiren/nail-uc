@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuanian Textile Enterprises (LT_TEXT)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LITHUANIAN TEXTILE ENTERPRISES (LT_TEXT)
echo   Input:   LT_TEXT_INLT_2COL.csv (1,429 companies)
echo   Output:  LT_TEXT_GMAP_1ENR.csv + LT_TEXT_GMAP_2COL.csv
echo            LT_TEXT_GMAP_ONLY_EMAILS_READY.csv + Sync LT_TEXT_INLT_2COL.csv
echo   Method:  Strict Name Matching + Visual Chrome + Multi-Tier Email Crawl
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please create .venv and install dependencies first.
    pause
    exit /b 1
)

if not exist "LT_TEXT_INLT_2COL.csv" (
    echo [ERROR] LT_TEXT_INLT_2COL.csv not found in workspace root!
    pause
    exit /b 1
)

echo [1/2] Checking core Python dependencies...
.venv\Scripts\python.exe -c "import playwright, curl_cffi, bs4, pandas" 2>nul
if errorlevel 1 (
    echo [*] Installing missing packages into .venv...
    .venv\Scripts\pip install playwright curl_cffi beautifulsoup4 pandas
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - headless=False)...
echo Chrome will open visibly so you can monitor progress and solve Captcha if needed.
echo Checkpoints are saved after each company (JSON) and every 5 companies (CSV).
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_text.py %*

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Outputs saved and synced:
echo     - LT_TEXT_GMAP_1ENR.csv (Master enriched dataset)
echo     - LT_TEXT_GMAP_2COL.csv (20-col Cold Mail, 100%% emails at top)
echo     - LT_TEXT_GMAP_ONLY_EMAILS_READY.csv (Only companies with email)
echo     - LT_TEXT_INLT_2COL.csv (Synced updated file)
echo     - csdl_mlt\ + archive\lt_lithuania\
echo =======================================================================
pause

