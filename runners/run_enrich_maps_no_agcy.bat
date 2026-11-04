@echo off
chcp 65001 >nul
title Google Maps and Web Email Enrichment - Norway HR Agencies

echo ========================================================
echo   GOOGLE MAPS AND WEB EMAIL ENRICHMENT - NORWAY HR
echo   Input: NO_AGCY_WEBD_2COL.csv (Master 5,003 agencies)
echo   Output 1ENR: NO_AGCY_GMAP_1ENR.csv
echo   Output 2COL: NO_AGCY_WEBD_2COL.csv (Cold Mail Ready)
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
%PYTHON_EXE% crawlmail\enrich_maps_no_agcy.py

echo.
echo Process completed!
pause

