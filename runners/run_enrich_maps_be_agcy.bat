@echo off
chcp 65001 >nul
title Google Maps and Web Email Enrichment - Belgium HR Agencies

echo ========================================================
echo   GOOGLE MAPS AND WEB EMAIL ENRICHMENT - BELGIUM HR
echo   Input: BE_AGCY_COMB_0RAW.csv
echo   Output 1ENR: BE_AGCY_GMAP_1ENR.csv
echo   Output 2COL: BE_AGCY_GMAP_2COL.csv (Cold Mail Ready)
echo   Incremental Auto-Save: Every 5 companies
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Google Maps and Web Email Enrichment...
%PYTHON_EXE% crawlmail\enrich_maps_be_agcy.py

echo.
echo Process completed!
pause
