@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuanian Restaurants and Food Service (LT_FOOD)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LITHUANIAN RESTAURANTS AND FOOD SERVICE
echo   Dataset: LT_FOOD_INLT_2COL.csv + LT_FOOD_INLT_1ENR.csv
echo   Method: Strict Matching + Visual Chrome + Anti-Aggregator Blacklist
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file LT_FOOD_INLT_2COL.csv...
if not exist "LT_FOOD_INLT_2COL.csv" (
    echo [ERROR] LT_FOOD_INLT_2COL.csv does not exist!
    echo Please run enrich_infolt_lt_food.py first to generate the base dataset.
    pause
    exit /b 1
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - Headless=False)...
echo You can observe Chrome searching, matching, and extracting official webs and phones.
echo Auto-saves checkpoints every 5 companies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_food.py %*

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
echo     - LT_FOOD_GMAP_1ENR.csv (Full enriched dataset)
echo     - LT_FOOD_GMAP_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo     - LT_FOOD_GMAP_ONLY_EMAILS_READY.csv (Outreach-ready rows)
echo     - Synchronized back to LT_FOOD_INLT_2COL.csv
echo =======================================================================
pause
