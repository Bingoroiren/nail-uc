@echo off
title Albania Hotel and Lodging Google Maps Scraper and Email Enricher
cd /d "%~dp0.."

echo ======================================================================
echo    ALBANIA HOTEL AND ACCOMMODATION GOOGLE MAPS AND EMAIL SCRAPER
echo ======================================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [-] Error: Python is not installed or not in PATH!
    pause
    exit /b 1
)

:: 2. Check / Create Virtual Environment
if not exist .venv (
    echo [*] Creating virtual environment .venv...
    python -m venv .venv
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:: 3. Install Requirements
echo [*] Checking required dependencies...
pip install -r requirements.txt >nul 2>&1
playwright install chromium >nul 2>&1

echo.
echo ======================================================================
echo    STEP 1: RUNNING GOOGLE MAPS HOTEL SCRAPER (ALBANIA)
echo    (Chrome browser will open for visual monitoring and captcha check)
echo ======================================================================
echo.
python src/scraper_hotel_al.py

echo.
echo ======================================================================
echo    STEP 2: ENRICHING EMAILS AND FORMATTING TO 20-COLUMN COLD MAIL
echo ======================================================================
echo.
python formatters/format_hotel_al_emails.py

echo.
echo ======================================================================
echo    ALBANIA HOTEL SCRAPER CAMPAIGN COMPLETED SUCCESSFULLY!
echo    Outputs:
echo      - data/raw/hotel_albania.csv
echo      - data/formatted/hotel_albania_with_emails_formatted.csv
echo      - Khach san Albania - ColdMail.csv
echo ======================================================================
pause
