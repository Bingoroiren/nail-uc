@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuanian Wood and Furniture (LT_WOOD_GMAP)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LITHUANIAN WOOD AND FURNITURE ENTERPRISES
echo   Input:   LT_WOOD_COMB_0RAW.csv
echo   Output:  LT_WOOD_GMAP_1ENR.csv + LT_WOOD_GMAP_2COL.csv
echo   Method:  Strict Matching + Visual Chrome + Multi-Tier Email Crawling
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file LT_WOOD_COMB_0RAW.csv...
if not exist "LT_WOOD_COMB_0RAW.csv" (
    echo [ERROR] LT_WOOD_COMB_0RAW.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - Headless=False)...
echo You can observe Chrome searching, matching, and extracting official webs and phones.
echo Auto-saves checkpoints every 5 companies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_wood.py

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_WOOD_GMAP_1ENR.csv (Full enriched dataset)
echo     - LT_WOOD_GMAP_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo     - LT_WOOD_GMAP_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo     - csdl_mlt\LT_WOOD_GMAP_2COL.csv
echo =======================================================================
pause

