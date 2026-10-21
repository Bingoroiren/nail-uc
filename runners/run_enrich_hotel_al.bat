@echo off
title Albania Hotel Email Scraper and Formatter
cd /d "%~dp0.."

echo ======================================================================
echo    ALBANIA HOTEL EMAIL ENRICHMENT AND COLD MAIL FORMATTER
echo ======================================================================
echo.

:: Ensure Python is in PATH if installed locally
if exist "C:\Users\PC\python311\tools\python.exe" (
    set "PATH=C:\Users\PC\python311\tools;C:\Users\PC\python311\tools\Scripts;%PATH%"
)

:: Activate Virtual Environment if it exists
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "%~dp0..\.venv\Scripts\activate.bat" call "%~dp0..\.venv\Scripts\activate.bat"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 goto NoPython

if not exist data\raw\hotel_albania.csv goto NoRawData

echo ======================================================================
echo    STEP 1: PREPROCESSING, DEDUPLICATION AND OTA FILTERING (CRAWLMAIL)
echo ======================================================================
echo.
python crawlmail/preprocess_csv_hotel_al.py
if errorlevel 1 goto PreprocessError

echo.
echo ======================================================================
echo    STEP 2: MULTI-TIER EMAIL SCRAPING (WEBSITE AND FACEBOOK FANPAGE)
echo    (Timeout extended for VPN stability)
echo ======================================================================
echo.
python crawlmail/email_scraper.py data/raw/hotel_albania.csv data/formatted/hotel_albania_with_emails.csv
if errorlevel 1 goto ScrapeMailError

echo.
echo ======================================================================
echo    STEP 3: STRICT FILTERING, SCORING AND 20-COLUMN COLD MAIL EXPORT
echo ======================================================================
echo.
python formatters/format_hotel_al_emails.py
if errorlevel 1 goto EnrichError

echo.
echo ======================================================================
echo    EMAIL ENRICHMENT COMPLETED SUCCESSFULLY!
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

:NoRawData
echo.
echo [-] Error: File data\raw\hotel_albania.csv not found!
echo [-] Please run run_hotel_al.bat to scrape Google Maps first.
pause
exit /b 1

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
