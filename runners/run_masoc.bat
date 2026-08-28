@echo off
chcp 65001 > nul
echo ============================================================
echo  MASOC Scraper + Formatter
echo  MASOC - Latvia Mechanical Engineering Member Database
echo ============================================================
echo.

cd /d "%~dp0.."
set "PATH=C:\Users\PC\python311\tools;%PATH%"

echo [1/2] Scraping MASOC member database...
python crawlmail\scrape_masoc.py
if errorlevel 1 (
    echo [ERROR] Scraper failed!
    pause
    exit /b 1
)

echo.
echo [2/2] Formatting output...
python formatters/format_masoc_emails.py
if errorlevel 1 (
    echo [ERROR] Formatter failed!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  DONE! Files created:
echo    masoc_members.csv         - Raw scraped data
echo    masoc_members_formatted.csv - Formatted for cold mail
echo ============================================================
pause
