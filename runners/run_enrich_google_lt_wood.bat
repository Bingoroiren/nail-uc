@echo off
chcp 65001 >nul
title Google Search Email Enrichment - Lithuanian Wood Enterprises (LT_WOOD_GSEA)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE SEARCH B2B EMAIL ENRICHMENT - LITHUANIAN WOOD ENTERPRISES
echo   Input:   LT_WOOD_GMAP_1ENR.csv
echo   Output:  LT_WOOD_GSEA_1ENR.csv + LT_WOOD_GSEA_2COL.csv
echo   Method:  Exact Name Query + SERP Delimiter Match + On-Page Verification
echo   Network: VPN Delay Optimized + Visual Chrome + Smart Captcha Pause
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file LT_WOOD_GMAP_1ENR.csv...
if not exist "LT_WOOD_GMAP_1ENR.csv" (
    echo [ERROR] LT_WOOD_GMAP_1ENR.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Google Search Enrichment (Visual Mode - Headless=False)...
echo You can observe Chrome searching Google, verifying on-page company names, and extracting B2B emails.
echo If a Google Captcha appears, the script will pause, ring an alert, and auto-resume once solved.
echo Auto-saves checkpoints every 5 companies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\enrich_google_lt_wood.py %*

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_WOOD_GSEA_1ENR.csv (Full enriched dataset)
echo     - LT_WOOD_GSEA_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo     - LT_WOOD_GSEA_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo     - Synced to LT_WOOD_GMAP_2COL.csv and csdl_mlt\
echo =======================================================================
pause

