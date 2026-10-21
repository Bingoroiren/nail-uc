@echo off
chcp 65001 >nul
title Google Maps Enrichment - Croatia Employment Agencies
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS DATA ENRICHMENT - CROATIA EMPLOYMENT AGENCIES
echo   Dataset: HR_AGCY_1ENR.csv
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target file HR_AGCY_1ENR.csv...
if not exist "HR_AGCY_1ENR.csv" (
    echo [ERROR] HR_AGCY_1ENR.csv does not exist!
    pause
    exit /b 1
)

echo [2/2] Launching Google Maps Enrichment (Visual Mode - Headless=False)...
echo You can minimize or observe Chrome while it finds Web, Phone and Emails.
echo Checkpoints are automatically saved every 3 agencies.
echo.
.venv\Scripts\python.exe crawlmail\enrich_maps_hr_agcy.py

echo.
echo =======================================================================
echo   ENRICHMENT PROCESS COMPLETED OR STOPPED SAFELY
echo   Data saved to: HR_AGCY_1ENR.csv (100%% emails sorted on top)
echo =======================================================================
pause
