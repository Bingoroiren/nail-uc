@echo off
chcp 65001 >nul
title Scraper Lithuanian Fabricated Metal Enterprises - litorg.cc (LT_METL_LTOR)
cd /d "%~dp0\.."

echo =======================================================================
echo   SCRAPER LITHUANIAN FABRICATED METAL ENTERPRISES (NACE 25)
echo   Source:  https://litorg.cc/en/catalog/25/
echo   Output:  LT_METL_LTOR_0RAW.csv + LT_METL_LTOR_2COL.csv
echo   Anti-Loop: Launching Native Google Chrome with CDP Port 9222
echo   Storage: Incremental Auto-Save + Checkpoint Cache
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

echo [1/2] Launching Genuine Native Google Chrome on Port 9222...
echo (This opens genuine Chrome directly to avoid Cloudflare Turnstile bot loop)
start "" "%CHROME_EXE%" --remote-debugging-port=9222 --user-data-dir="%~dp0..\chrome_user_data\native_chrome" "https://litorg.cc/en/catalog/25/"

echo Waiting 3 seconds for Chrome to initialize...
timeout /t 3 /nobreak >nul

echo.
echo [2/2] Connecting Scraper to Native Chrome...
echo Please look at the opened Chrome window. If "Verify you are human" appears,
echo click it ONCE. Genuine Chrome passes Cloudflare Turnstile instantly without looping!
echo.
.venv\Scripts\python.exe src\scraper_lt_metal_litorg.py --cdp-port 9222 %*

echo.
echo =======================================================================
echo   SCRAPING COMPLETED OR STOPPED SAFELY
echo   Data saved to:
echo     - LT_METL_LTOR_0RAW.csv (Raw dataset)
echo     - LT_METL_LTOR_2COL.csv (Standard 20-col Cold Mail)
echo     - LT_METL_LTOR_ONLY_EMAILS_READY.csv (Ready cold mail emails)
echo     - Synced to csdl_mlt\ and archive\lt_lithuania\
echo =======================================================================
pause
