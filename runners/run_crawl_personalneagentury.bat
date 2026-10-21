@echo off
chcp 65001 >nul
title PersonalneAgentury.sk Scraper - Slovakia Employment Agencies
echo =======================================================================
echo   SCRAPER: PERSONALNEAGENTURY.SK - SLOVAKIA EMPLOYMENT AGENCIES
echo   Visual Mode (Headless=False) - Cloudflare Turnstile Auto-Handling
echo =======================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in .venv!
    pause
    exit /b 1
)

echo Starting crawler...
.venv\Scripts\python.exe crawlmail\crawl_personalneagentury.py %*

echo.
echo =======================================================================
echo   CRAWLING COMPLETED OR CHECKPOINT SAVED!
echo   Output files:
echo   - SK_AGCY_PERS_0RAW.csv
echo   - SK_AGCY_PERS_2COL.csv
echo =======================================================================
pause
