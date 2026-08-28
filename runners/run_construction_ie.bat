@echo off
set "PATH=C:\Users\PC\python311\tools;%PATH%"
title Ireland Construction and Manufacturing Scraper Launcher
cd /d "%~dp0.."

echo ======================================================
echo       AUTOMATIC PYTHON SETUP AND SCRAPER RUN (CONSTRUCTION IE)
echo ======================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: Create Virtual Environment if it doesn't exist
if exist .venv goto ActivateVenv
echo [*] Creating virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 goto VenvFailed

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install Requirements
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
echo ======================================================
echo STEP 1: Launching Ireland Construction and Manufacturing Maps Scraper...
echo ======================================================
python -u src/scraper_construction_ie.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 2: Preprocessing and Strict Category Filtering...
echo ======================================================
python crawlmail/preprocess_csv_construction_ie.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 3: Launching Email Scraper for Ireland Construction...
echo ======================================================
python crawlmail/email_scraper.py data/raw/construction_ireland.csv data/formatted/construction_ireland_with_emails.csv
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 4: Formatting, Scoring and Translating Tags...
echo ======================================================
python formatters/format_construction_ie_emails.py
if errorlevel 1 goto RunFailed

goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
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
echo [ERROR] Scraping pipeline failed during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo   IRELAND CONSTRUCTION SCRAPING SESSION TERMINATED
echo ======================================================
pause
