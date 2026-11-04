@echo off
chcp 65001 >nul
title Herold Austria Nail Salons Scraper (73 Pages)
cd /d "%~dp0\.."

echo ======================================================================
echo    HEROLD AUSTRIA NAIL SALONS SCRAPER (73 PAGES)
echo    Source: herold.at/gelbe-seiten/nagelstudio/
echo    Output: data\AT_NAIL_HERO_0RAW.csv
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found!
    pause
    exit /b 1
)

echo [*] Activating Python virtual environment...
call .venv\Scripts\activate.bat

echo [*] Scraping 73 pages from Herold.at...
echo.
python -u src\scraper_nail_herold_at.py
if errorlevel 1 (
    echo.
    echo [ERROR] Herold scraper encountered an error!
    pause
    exit /b 1
)

echo.
echo [*] Consolidating all Austria nail salons into master dataset...
python -u formatters\format_nail_austria_master.py

echo.
echo ======================================================================
echo [SUCCESS] Herold scraping and consolidation completed!
echo ======================================================================
echo.
pause

