@echo off
title Albania Hotel and Lodging Google Maps Scraper and Email Enricher
cd /d "%~dp0.."

echo ======================================================================
echo    ALBANIA HOTEL AND ACCOMMODATION GOOGLE MAPS AND EMAIL SCRAPER
echo ======================================================================
echo.

:: Ensure Python is in PATH if installed locally
if exist "C:\Users\PC\python311\tools\python.exe" (
    set "PATH=C:\Users\PC\python311\tools;C:\Users\PC\python311\tools\Scripts;%PATH%"
)

:: Activate Virtual Environment if it exists
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "%~dp0..\.venv\Scripts\activate.bat" call "%~dp0..\.venv\Scripts\activate.bat"

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 goto NoPython

:: 2. Check / Create Virtual Environment
if not exist .venv (
    echo [*] Creating virtual environment .venv...
    python -m venv .venv
    call .venv\Scripts\activate.bat
)

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
if errorlevel 1 goto ScraperError

if not exist data\raw\hotel_albania.csv goto NoRawData

echo.
echo ======================================================================
echo    STEP 2: PREPROCESSING, DEDUPLICATION AND OTA FILTERING (CRAWLMAIL)
echo ======================================================================
echo.
python crawlmail/preprocess_csv_hotel_al.py
if errorlevel 1 goto PreprocessError

echo.
echo ======================================================================
echo    STEP 3: MULTI-TIER EMAIL SCRAPING (WEBSITE AND FACEBOOK FANPAGE)
echo ======================================================================
echo.
python crawlmail/email_scraper.py data/raw/hotel_albania.csv data/formatted/hotel_albania_with_emails.csv
if errorlevel 1 goto ScrapeMailError

echo.
echo ======================================================================
echo    STEP 4: STRICT FILTERING, SCORING AND 20-COLUMN COLD MAIL EXPORT
echo ======================================================================
echo.
python formatters/format_hotel_al_emails.py
if errorlevel 1 goto EnrichError

echo.
echo ======================================================================
echo    ALBANIA HOTEL SCRAPER CAMPAIGN COMPLETED SUCCESSFULLY!
echo    Outputs:
echo      - data/raw/hotel_albania.csv
echo      - data/formatted/hotel_albania_with_emails.csv
echo      - data/formatted/hotel_albania_with_emails_formatted.csv
echo      - Khach san Albania - ColdMail.csv
echo ======================================================================
goto End

:NoPython
echo [-] Error: Python is not installed or not in PATH!
pause
exit /b 1

:ScraperError
echo.
echo [-] Google Maps scraper was stopped or encountered an error.
echo [-] Skipping Step 2.
pause
exit /b 1

:NoRawData
echo.
echo [*] No raw data file found yet (scraper might have been closed early).
echo [*] Exiting cleanly. Run again whenever you are ready!
pause
exit /b 0

:PreprocessError
echo.
echo [-] Preprocessing and deduplication step encountered an error.
pause
exit /b 1

:ScrapeMailError
echo.
echo [-] Multi-tier email scraper encountered an error.
pause
exit /b 1

:EnrichError
echo.
echo [-] Email formatting and export step encountered an error.
pause
exit /b 1

:End
pause
