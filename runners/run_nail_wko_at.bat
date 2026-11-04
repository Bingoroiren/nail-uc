@echo off
chcp 65001 >nul
title WKO Austria Nail Salons Scraper (All 9 States)
cd /d "%~dp0\.."

echo ======================================================================
echo    WKO AUSTRIA NAIL SALONS SCRAPER (ALL 9 STATES)
echo    Source: firmen.wko.at/nagelstudio/
echo    Output: AT_NAIL_WKOP_0RAW.csv + AT_NAIL_WKOP_2COL.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found!
    pause
    exit /b 1
)

echo [*] Activating Python virtual environment...
call .venv\Scripts\activate.bat

echo [*] STEP 1: Scraping all 9 Austrian states from WKO...
echo.
python -u src\scraper_nail_wko_at.py
if errorlevel 1 (
    echo.
    echo [ERROR] Scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo [*] STEP 2: Formatting data to Cold Mail 20-column standard...
echo.
python -u formatters\format_nail_wko_at.py
if errorlevel 1 (
    echo.
    echo [ERROR] Formatting encountered an error!
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo [SUCCESS] WKO Nail Salons scraping completed successfully!
echo Files generated:
echo  - AT_NAIL_WKOP_0RAW.csv (Raw data)
echo  - AT_NAIL_WKOP_2COL.csv (Full 20-col master)
echo  - AT_NAIL_WKOP_ONLY_EMAILS_READY.csv (100%% verified emails ready)
echo  - csdl_mlt\AT_NAIL_WKOP_2COL.csv
echo  - csdl_mlt\AT_NAIL_WKOP_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.
pause

