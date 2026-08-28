@echo off
title Taiwan WDA Employer Database Scraper Launcher
cd /d "%~dp0.."
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ======================================================
echo         AUTOMATIC PYTHON SETUP AND SCRAPER RUN (WDA)
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
echo ======================================================
echo Launching Taiwan WDA Employer Database Scraper...
echo ======================================================
python scrapers_standalone/scrape_wda_employers.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo Scoring and Sorting Leads (Quota Hunter Rating)...
echo ======================================================
python filter_wda_hot_leads.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo Formatting Results to standard template...
echo ======================================================
python formatters/format_wda_emails.py
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
echo       TAIWAN WDA SCRAPING SESSION TERMINATED
echo ======================================================
pause
