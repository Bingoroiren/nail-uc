@echo off
chcp 65001 >nul
title Pre-Maps Enrichment - Norway HR Agencies

echo ========================================================
echo   PRE-MAPS ENRICHMENT - NORWAY RECRUITMENT AGENCIES
echo   Input: NO_AGCY_WEBD_0RAW.csv
echo   Output 1ENR: NO_AGCY_WEBD_1ENR.csv
echo   Output 2COL: NO_AGCY_WEBD_2COL.csv (Cold Mail Ready)
echo   Incremental Auto-Save: Every 10 companies
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Pre-Maps Enrichment...
%PYTHON_EXE% crawlmail\enrich_no_agcy_webd.py

echo.
echo Process completed!
pause

