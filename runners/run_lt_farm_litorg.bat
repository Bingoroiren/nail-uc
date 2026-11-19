@echo off
rem Launcher for Lithuanian Agriculture and Farming Enterprises Scraper (NACE Division 01)
rem Source: https://litorg.cc/en/catalog/01/
rem Output: LT_FARM_LTOR_0RAW.csv and LT_FARM_LTOR_2COL.csv
cd /d "%~dp0\.."

echo ==============================================================================
echo LITORG.CC SCRAPER - NACE 01 AGRICULTURE, FARMING AND CROPS (LT_FARM_LTOR)
echo Target : https://litorg.cc/en/catalog/01/
echo Scope  : Crop and animal production, hunting and related service activities
echo Storage: Incremental Auto-Save and Checkpoint Cache
echo ==============================================================================
echo.

set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
if not exist "%CHROME_EXE%" (
    set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

powershell -NoProfile -Command "if ((Test-NetConnection 127.0.0.1 -Port 9222 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo [1/2] Starting genuine Google Chrome with remote debugging on port 9222...
    start "" "%CHROME_EXE%" --remote-debugging-port=9222 --user-data-dir="%~dp0..\chrome_user_data\native_chrome" "https://litorg.cc/en/catalog/01/"
    echo.
    echo Please check the opened Chrome window. If "Verify you are human" appears,
    echo click it once to pass Cloudflare Turnstile verification.
    echo.
    echo Press any key after Cloudflare verification is done to start scraping...
    pause
)

echo.
echo [2/2] Running Python Scraper via Chrome CDP (port 9222)...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\scraper_lt_farm_litorg.py --cdp-port 9222 %*
) else (
    python src\scraper_lt_farm_litorg.py --cdp-port 9222 %*
)

echo.
echo ==============================================================================
echo Scraping finished or stopped safely.
echo Output datasets generated:
echo   - LT_FARM_LTOR_0RAW.csv (Raw catalog dataset)
echo   - LT_FARM_LTOR_2COL.csv (Standard 20-col Cold Mail format)
echo   - LT_FARM_LTOR_ONLY_EMAILS_READY.csv (Companies with valid email)
echo   - Synced to csdl_mlt\ and archive\lt_lithuania\
echo ==============================================================================
pause
