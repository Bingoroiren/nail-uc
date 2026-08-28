@echo off
title Latvia Construction Company Google Maps & Email Scraper Launcher
cd /d "%~dp0.."
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo         AUTOMATIC PYTHON SETUP AND SCRAPER RUN (CONSTRUCTION LV)
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
echo [SUCCESS] Environment is fully configured!
echo ======================================================
echo STEP 1: Launching Latvia Construction Google Maps Scraper...
echo ======================================================
python -u src/scraper_construction_lv.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 2: Preprocessing Scraped Latvia Businesses...
echo ======================================================
python crawlmail/preprocess_csv_construction_lv.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 3: Launching Email Scraper for Latvia Construction...
echo ======================================================
python crawlmail/email_scraper.py data/raw/construction_latvia.csv data/formatted/construction_latvia_with_emails.csv
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo STEP 4: Formatting and Translating Results...
echo ======================================================
python formatters/format_construction_lv_emails.py
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
echo [ERROR] Scraping pipeline failed during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo       LATVIA CONSTRUCTION SCRAPING SESSION TERMINATED
echo ======================================================
pause
