@echo off
title Naver Map Recruiter Scraper Launcher
cd /d "%~dp0"

echo ======================================================
echo         AUTOMATIC PYTHON SETUP AND SCRAPER RUN (NAVER MAP)
echo ======================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: Activate Virtual Environment if it exists
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
echo STEP 1: Launching Naver Map Scraper...
echo ======================================================
python src/scraper_naver.py
if errorlevel 1 goto RunFailed

echo ======================================================
echo STEP 2: Scrape Emails and Format Korean Agencies Data...
echo ======================================================
python format_korean_emails.py
if errorlevel 1 goto FormatFailed

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

:FormatFailed
echo [ERROR] Email scraping or formatting step failed during execution.
pause
exit /b

:End
echo.
echo ======================================================
echo         NAVER MAP SCRAPING SESSION TERMINATED
echo ======================================================
pause
