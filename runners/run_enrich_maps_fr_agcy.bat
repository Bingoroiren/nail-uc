@echo off
chcp 65001 >nul
title Google Maps and Email Enrichment - France Recruitment and Interim Agencies

cd /d "%~dp0\.."

echo ======================================================================
echo    GOOGLE MAPS AND B2B EMAIL ENRICHMENT (FR_AGCY_PJAU)
echo    Input:  FR_AGCY_PJAU_0RAW.csv (560 companies)
echo    Output: FR_AGCY_PJAU_1ENR.csv
echo            FR_AGCY_PJAU_2COL.csv (Cold Mail 20 Columns)
echo            FR_AGCY_PJAU_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe crawlmail\enrich_maps_fr_agcy.py

echo.
echo ======================================================================
echo    ENRICHMENT COMPLETED
echo ======================================================================
pause
