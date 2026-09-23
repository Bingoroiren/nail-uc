@echo off
title Albania Labor Recruitment Google Maps ^& Email Scraper Launcher
cd /d "%~dp0.."

echo ======================================================
echo       AUTOMATIC SETUP AND SCRAPER RUN (ALBANIA BROKERS)
echo ======================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: Activate Virtual Environment if it exists or create one
if exist .venv goto ActivateVenv
echo [*] Creating virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 goto VenvFailed

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install Dependencies
echo [*] Upgrading pip...
python -m pip install --upgrade pip >nul

echo [*] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 goto DependenciesFailed

:: Install Playwright Chromium Driver
echo [*] Checking/installing Playwright browser driver (Chromium)...
playwright install chromium
if errorlevel 1 goto PlaywrightFailed

echo.
echo [SUCCESS] Environment is fully configured!
echo ======================================================
echo STEP 1: Launching Albania Labor Recruitment Google Maps Scraper...
echo ======================================================
python -u src/scraper_broker_al.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 2: Preprocessing and Strict Category Filtering...
echo ======================================================
python crawlmail/preprocess_csv_broker_al.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 3: Launching Email Scraper for Albania Brokers...
echo ======================================================
python crawlmail/email_scraper.py data/raw/broker_albania.csv data/formatted/broker_albania_with_emails.csv
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 4: Formatting, Translating Tags and Generating Excel...
echo ======================================================
python formatters/format_broker_al_emails.py
if errorlevel 1 goto RunFailed

goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
echo Please install Python 3.8+ and check "Add Python to PATH" during installation.
pause
exit /b

:VenvFailed
echo [ERROR] Failed to create virtual environment.
pause
exit /b

:DependenciesFailed
echo [ERROR] Failed to install dependencies.
pause
exit /b

:PlaywrightFailed
echo [ERROR] Failed to install Playwright Chromium driver.
pause
exit /b

:RunFailed
echo [ERROR] Scraping pipeline encountered an error during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo     ALBANIA BROKER SCRAPING SESSION TERMINATED SUCCESSFULLY
echo ======================================================
pause
