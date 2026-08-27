@echo off
title Find Missing Latvia Fish Factories on Google Maps
cd /d "%~dp0"
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo   FIND MISSING LATVIA FISH FACTORIES ON GOOGLE MAPS
echo ======================================================

:: Check virtual environment
if not exist .venv (
    echo [ERROR] Virtual environment .venv not found. Please run run_fisheries_lv.bat first to configure it.
    pause
    exit /b
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Running scraper to find missing factories on Google Maps...
python src/find_missing_fisheries.py

echo.
echo ======================================================
echo   SCRAPING SESSION COMPLETE
echo ======================================================
pause
