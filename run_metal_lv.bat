@echo off
title Latvia Metalworking Google Maps + Email Scraper Pipeline
chcp 65001 > nul
cd /d "%~dp0"
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo ============================================================
echo   LATVIA METALWORKING / METAL FABRICATION SCRAPER PIPELINE
echo   Tag chinh: Meta^la darbn^ica (Xuong gia cong kim loai)
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
echo STEP 1: Google Maps Scraper - Latvia Metalworking Companies
echo         Keywords: Meta^la darbn^ica, Meta^lapstrade, etc.
echo         Zoom: 10 (wider coverage)
echo ============================================================
python -u src/scraper_metal_lv.py %*
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 2: Preprocessing Scraped Data
echo         - Remove duplicates
echo         - Strict category filter
echo         - Format phone numbers
echo ============================================================
python crawlmail/preprocess_csv_metal_lv.py
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 3: Email Scraper
echo         Visits each company website to extract email
echo ============================================================
python crawlmail/email_scraper.py metal_latvia.csv metal_latvia_with_emails.csv
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo STEP 4: Format Output (standard cold-mail template)
echo         Category translated to Vietnamese
echo         Compatible with masoc_members_formatted.csv
echo ============================================================
python format_metal_lv_emails.py
if errorlevel 1 goto RunFailed

echo.
echo ============================================================
echo  PIPELINE COMPLETE! Files created:
echo    metal_latvia.csv                     - Raw Google Maps data
echo    metal_latvia_with_emails.csv         - With emails scraped
echo    metal_latvia_with_emails_formatted.csv - Final formatted output
echo.
echo  Note: Metal entries have been AUTOMATICALLY merged
echo        into masoc_members_formatted.csv.
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
echo    LATVIA METALWORKING SCRAPING SESSION COMPLETE
echo ============================================================
pause
