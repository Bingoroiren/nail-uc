@echo off
chcp 65001 >nul
title KBO Belgium HR and Agency Scraper

echo ========================================================
echo   KBO BELGIUM RECRUITMENT AND STAFFING SCRAPER
echo   Codes: 78.100, 78.200, 78.300
echo   Model Agencies / Mannequins: Excluded Automatically
echo   Permanent Blacklist: Excluded Automatically
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting KBO Belgium Scraper across all Belgian postcodes...
%PYTHON_EXE% src\scraper_agcy_be.py

echo.
echo Process finished. Check output file: BE_AGCY_KBO0_0RAW.csv
pause
