@echo off
title Slovakia Auto and Aluminum Factories Google Maps Scraper Launcher
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA AUTO FACTORIES AND ALUMINUM FRAMES PIPELINE
echo    Market: Slovakia
echo    Keywords: Tovaren na automobily, Automobilovy servis,
echo              Restaurovanie automobilov, Dodavatel hlinikovych ramov,
echo              Autolakovna
echo ======================================================

python --version >nul 2>&1
if errorlevel 1 goto NoPython

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Checking Playwright Chromium...
playwright install chromium >nul 2>&1

echo.
echo ======================================================
echo STEP 1: Launching Slovakia Auto Google Maps Scraper...
echo ======================================================
python -u src/scraper_auto_sk.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 2: Preprocessing Scraped Slovakia Businesses...
echo ======================================================
python -u crawlmail/preprocess_csv_auto_sk.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 3: Launching Deep Email Scraper for Slovakia Auto...
echo ======================================================
python -u crawlmail/email_scraper.py data/raw/SK_AUTO_GMAP_0RAW.csv data/formatted/SK_AUTO_GMAP_1ENR.csv
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 4: Formatting and Translating Results...
echo ======================================================
python -u formatters/format_auto_sk_emails.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    SLOVAKIA AUTO SCRAPING AND ENRICHMENT COMPLETE!
echo    Final File: data/formatted/SK_AUTO_GMAP_2COL.csv and SK_AUTO_GMAP_2COL.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Scraping pipeline failed during execution.
pause
exit /b

:End
