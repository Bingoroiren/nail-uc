@echo off
cd /d "%~dp0\.."

echo ==============================================================================
echo LITORG.CC SCRAPER - NACE 52 WAREHOUSING AND TRANSPORT SUPPORT (LT_WARE_LTOR)
echo Source: https://litorg.cc/en/catalog/52/
echo ==============================================================================

powershell -NoProfile -Command "if ((Test-NetConnection 127.0.0.1 -Port 9222 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo Starting native Chrome on CDP port 9222...
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%CD%\chrome_user_data\native_chrome" --remote-debugging-port=9222 "https://litorg.cc/en/catalog/52/"
    echo.
    echo Please verify Cloudflare in the Chrome window if prompted until the company list appears.
    pause
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\scraper_lt_ware_litorg.py --cdp-port 9222 %*
) else (
    python src\scraper_lt_ware_litorg.py --cdp-port 9222 %*
)

echo.
echo Finished. Press any key to exit.
pause >nul

