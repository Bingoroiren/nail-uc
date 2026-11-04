@echo off
chcp 65001 >nul
title Austria Nail Salons Google Maps Scraper and Email Enrichment Pipeline
cd /d "%~dp0\.."

echo ======================================================================
echo    AUSTRIA NAIL SALONS GOOGLE MAPS AND EMAIL PIPELINE
echo    Market: Austria (AT)
echo    Keyword: Nagelstudio
echo    Standard: UTF-8 with BOM, Phone with single quote, 20 Cold Mail cols
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Ensuring Playwright Chromium is ready...
playwright install chromium >nul 2>&1

echo.
echo ======================================================================
echo STEP 1: Launching Google Maps Scraper (Visual mode)...
echo ======================================================================
python -u src\scraper_nail_at.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo STEP 2: Preprocessing and Deduplicating Raw Data...
echo ======================================================================
python -u crawlmail\preprocess_csv_nail_at.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo STEP 3: Deep Web Email Scraping (Impressum and Contact Pages)...
echo ======================================================================
python -u crawlmail\email_scraper.py data\formatted\AT_NAIL_GMAP_0RAW_clean.csv data\formatted\AT_NAIL_GMAP_1ENR.csv
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo STEP 4: Standardizing into 20-Column Cold Mail Format...
echo ======================================================================
python -u formatters\format_nail_at_emails.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] AUSTRIA NAIL SALONS PIPELINE COMPLETED SUCCESSFULLY!
echo Final files:
echo  - data\formatted\AT_NAIL_GMAP_2COL.csv
echo  - AT_NAIL_GMAP_2COL.csv
echo  - csdl_mlt\AT_NAIL_GMAP_2COL.csv
echo  - archive\at_austria\AT_NAIL_GMAP_2COL.csv
echo ======================================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Pipeline encountered an error during execution!
pause
exit /b 1

:End

