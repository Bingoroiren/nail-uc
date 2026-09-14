@echo off
chcp 65001 > NUL
cd /d "%~dp0\.."
echo ==================================================
echo Starting WKO Austria Temporary Staffing Agencies Scraper (agency_at)
echo ==================================================

call .venv\Scripts\activate.bat

echo [*] Step 1: Scraping WKO Agency Profiles...
python -u src\scraper_agency_at.py %*

if %ERRORLEVEL% NEQ 0 (
    echo [-] Error occurred during directory scraping.
    exit /b %ERRORLEVEL%
)

echo.
echo [*] Step 2: Crawling Website Emails & Formatting CSV...
python -u formatters\format_agency_at_emails.py %*

if %ERRORLEVEL% NEQ 0 (
    echo [-] Error occurred during email crawling / formatting.
    exit /b %ERRORLEVEL%
)

echo.
echo ==================================================
echo [SUCCESS] Austria Agency Scraping & Formatting Completed!
echo Outputs:
echo   - data\formatted\agency_austria_with_emails_formatted.csv
echo   - data\formatted\agency_austria_clean_dedup.csv
echo ==================================================
pause
