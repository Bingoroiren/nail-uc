@echo off
chcp 65001 >nul
title FirmenABC Austria Nail Salons Scraper (412 Salons)
cd /d "%~dp0\.."

echo ======================================================================
echo    FIRMENABC AUSTRIA NAIL SALONS SCRAPER (412 SALONS)
echo    Source: firmenabc.at/suche/ergebnisse
echo    Output: data\AT_NAIL_FABC_0RAW.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found!
    pause
    exit /b 1
)

echo [*] Activating Python virtual environment...
call .venv\Scripts\activate.bat

echo [*] Scraping FirmenABC with visual Chromium...
echo.
python -u src\scraper_nail_fabc_at.py
if errorlevel 1 (
    echo.
    echo [ERROR] FirmenABC scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo [*] Consolidating all Austria nail salons into master dataset...
python -u formatters\format_nail_austria_master.py

echo.
echo ======================================================================
echo [SUCCESS] FirmenABC scraping and consolidation completed!
echo ======================================================================
echo.
pause

