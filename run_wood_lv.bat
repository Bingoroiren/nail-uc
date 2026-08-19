@echo off
title Latvia Woodworking Google Maps + Email Scraper Pipeline
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo   LATVIA WOODWORKING / CARPENTRY SCRAPER PIPELINE
echo   Tags: Galdniecība, Mēbeļu izgatavotājs, Galdnieks, 
echo         Kokmateriālu piegādātājs, Kokzāģētava
echo ============================================================
echo.

:: ---- Check Python ----
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: ---- Virtual Environment ----
if exist .venv goto ActivateVenv
echo [*] Creating virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 goto VenvFailed

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Upgrading pip...
python -m pip install --upgrade pip >nul

echo [*] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 goto DependenciesFailed

echo [*] Checking/installing Playwright Chromium driver...
playwright install chromium
if errorlevel 1 goto PlaywrightFailed

echo.
echo ============================================================
echo STEP 1: Google Maps Scraper - Latvia Woodworking Companies
echo         Keywords: Galdniecība, Mēbeļu izgatavotājs, etc.
echo         Zoom: 11 (standard coverage)
echo ============================================================
python -u src/scraper_wood_lv.py %*
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 2: Preprocessing Scraped Data
echo         - Remove duplicates
echo         - Strict category filter
echo         - Format phone numbers
echo ============================================================
python crawlmail/preprocess_csv_wood_lv.py
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 3: Email Scraper
echo         Visits each company website to extract email
echo ============================================================
python crawlmail/email_scraper.py wood_latvia.csv wood_latvia_with_emails.csv
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 4: Format Output (standard cold-mail template)
echo         Category translated to Vietnamese
echo         Compatible with masoc_members_formatted.csv
echo ============================================================
python format_wood_lv_emails.py
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo  PIPELINE COMPLETE! Files created:
echo    wood_latvia.csv                     - Raw Google Maps data
echo    wood_latvia_with_emails.csv         - With emails scraped
echo    wood_latvia_with_emails_formatted.csv - Final formatted output
echo.
echo  To merge into MASOC list, append the formatted CSV rows
echo  into masoc_members_formatted.csv manually in Excel.
echo ============================================================
goto End

:NoPython
echo [ERROR] Python is not installed or not in PATH.
pause & exit /b

:VenvFailed
echo [ERROR] Failed to create virtual environment.
pause & exit /b

:DependenciesFailed
echo [ERROR] Failed to install dependencies.
pause & exit /b

:PlaywrightFailed
echo [ERROR] Failed to install Playwright Chromium driver.
pause & exit /b

:RunFailed
echo [ERROR] Pipeline failed at this step.
pause & exit /b

:End
echo.
echo ============================================================
echo    LATVIA WOODWORKING SCRAPING SESSION COMPLETE
echo ============================================================
pause
