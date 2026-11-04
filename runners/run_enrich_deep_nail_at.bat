@echo off
chcp 65001 >nul
title Deep Email Scraper for Austria Nail Salons
cd /d "%~dp0\.."

echo ======================================================================
echo    DEEP EMAIL SCRAPER FOR AUSTRIA NAIL SALONS
echo    Target: AT_NAIL_GMAP_2COL.csv
echo    Scope: Deep crawl Austrian websites (Impressum, Kontakt, Preise)
echo           Auto-discover missing websites via DuckDuckGo
echo           Filter junk emails (webador, beispiel, chilly, netports)
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python.exe not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting deep email scraper...
echo.

python -u crawlmail\enrich_deep_nail_at.py %*
if errorlevel 1 goto RunFailed

echo.
echo ======================================================================
echo [SUCCESS] Deep email enrichment completed successfully!
echo Files updated:
echo  - AT_NAIL_ONLY_EMAILS_READY.csv
echo  - AT_NAIL_GMAP_2COL.csv
echo  - csdl_mlt\AT_NAIL_ONLY_EMAILS_READY.csv
echo  - archive\at_austria\AT_NAIL_ONLY_EMAILS_READY.csv
echo ======================================================================
echo.
pause
goto End

:RunFailed
echo.
echo [ERROR] Process encountered an error!
pause
exit /b 1

:End

