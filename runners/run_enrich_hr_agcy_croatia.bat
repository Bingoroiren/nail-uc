@echo off
chcp 65001 >nul
title Deep Multi-Tier Enrichment - Croatian Employment Agencies (HR_AGCY)
cd /d "%~dp0\.."

echo =======================================================================
echo   DEEP MULTI-TIER DATA ENRICHMENT - CROATIAN EMPLOYMENT AGENCIES
echo   Dataset: HR_AGCY_MROS_0RAW.csv + HR_AGCY_1ENR.csv
echo   Sources: CompanyWall.hr (OIB + Director) + Official Websites (crawl-mail)
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    echo Please install Python virtual environment first.
    pause
    exit /b 1
)

echo [1/2] Checking target dataset files...
if not exist "HR_AGCY_MROS_0RAW.csv" (
    if not exist "HR_AGCY_1ENR.csv" (
        echo [ERROR] Neither HR_AGCY_MROS_0RAW.csv nor HR_AGCY_1ENR.csv found!
        pause
        exit /b 1
    )
)

echo [2/2] Launching Deep Multi-Tier Enrichment (Multi-threaded curl_cffi)...
echo Auto-saves checkpoints every 10 agencies to cache and CSV.
echo.
.venv\Scripts\python.exe crawlmail\enrich_hr_agcy_croatia_deep.py

echo.
echo =======================================================================
echo   ENRICHMENT COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - HR_AGCY_MROS_1ENR.csv (Full enriched dataset with OIB and Director)
echo     - HR_AGCY_MROS_2COL.csv (Standard 20-col Cold Mail, 100%% emails on top)
echo =======================================================================
pause
