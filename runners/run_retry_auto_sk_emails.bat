@echo off
title Retry Scraping Empty Emails - Slovakia Auto
cd /d "%~dp0.."

echo ======================================================
echo    RETRY SCRAPING EMPTY EMAILS - SLOVAKIA AUTO
echo    Input: data/raw/SK_AUTO_GMAP_0RAW.csv
echo    Output: data/formatted/SK_AUTO_GMAP_1ENR.csv
echo    Mode: --retry-empty (Only scan companies with missing emails)
echo ======================================================

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b

:ActivateVenv
call .venv\Scripts\activate.bat

echo [*] Launching Email Scraper with --retry-empty...
python -u crawlmail/email_scraper.py data/raw/SK_AUTO_GMAP_0RAW.csv data/formatted/SK_AUTO_GMAP_1ENR.csv --retry-empty
if errorlevel 1 goto RunFailed

echo.
echo [*] Formatting and Translating Results...
python -u formatters/format_auto_sk_emails.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    RETRY COMPLETE!
echo    Final File: data/formatted/SK_AUTO_GMAP_2COL.csv and SK_AUTO_GMAP_2COL.csv
echo ======================================================
pause
goto End

:RunFailed
echo.
echo [ERROR] Email scraper failed during execution.
pause
exit /b

:End
