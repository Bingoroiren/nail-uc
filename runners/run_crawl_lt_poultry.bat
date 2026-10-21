@echo off
title Lithuania Poultry and Meat Processing Scraper
cd /d "%~dp0\.."

echo ======================================================
echo    LITHUANIA POULTRY AND MEAT PROCESSING SCRAPER
echo    Sources: info.lt, ensun.io, rekvizitai.vz.lt
echo    Output : LT_POUL_WEBD_0RAW.csv
echo    Feature: Visual Chrome + Manual Captcha Alert
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching scraper...
"%PYTHON_EXE%" -u crawlmail\crawl_lt_poultry.py

if errorlevel 1 (
    echo.
    echo [!] Scraper encountered an error.
    pause
    exit /b 1
)

echo.
echo [*] Scraping completed successfully!
pause
