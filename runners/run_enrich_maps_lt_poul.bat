@echo off
chcp 65001 >nul
title Google Maps Enrichment - Lithuanian Poultry and Meat Processing (LT_POUL_WEBD)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - LITHUANIAN POULTRY AND MEAT ENTERPRISES
echo   Dataset: LT_POUL_WEBD_1ENR.csv + LT_POUL_WEBD_2COL.csv
echo   Method: Strict Matching + Visual Chrome + Anti-Aggregator Blacklist
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file LT_POUL_WEBD_1ENR.csv...
if not exist "LT_POUL_WEBD_1ENR.csv" (
    echo [ERROR] LT_POUL_WEBD_1ENR.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - Headless=False)...
echo You can observe Chrome searching, matching, and extracting official webs and phones.
echo Auto-saves checkpoints every 5 companies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_lt_poul.py

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_POUL_WEBD_1ENR.csv (Full enriched dataset)
echo     - LT_POUL_WEBD_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo =======================================================================
pause
