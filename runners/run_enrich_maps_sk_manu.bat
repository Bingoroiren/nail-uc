@echo off
chcp 65001 >nul
title Google Maps Enrichment - Slovak Manufacturing (Auto + Mech + Metal)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS ENRICHMENT - SLOVAK MANUFACTURING FACTORIES
echo   Dataset: SK_MANU_SLVD_1ENR.csv (Auto + Mech + Metal)
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file SK_MANU_SLVD_1ENR.csv...
if not exist "SK_MANU_SLVD_1ENR.csv" (
    echo [ERROR] SK_MANU_SLVD_1ENR.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - Headless=False)...
echo You can observe Chrome finding Web, Phone and B2B Emails.
echo Checkpoints are automatically saved every 5 companies.
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_sk_manu.py

echo.
echo =======================================================================
echo   ENRICHMENT PROCESS COMPLETED OR STOPPED SAFELY
echo   Data saved to: SK_MANU_SLVD_1ENR.csv (100%% emails sorted on top)
echo =======================================================================
pause
