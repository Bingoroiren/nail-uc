@echo off
chcp 65001 >nul
title Google Maps and Web Email Enrichment - Norway Agriculture

echo ===============================================================================
echo        GOOGLE MAPS AND WEB EMAIL ENRICHMENT - NORWAY AGRICULTURE
echo                             (NO_FARM)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_maps_no_farm.py (Playwright visual mode)...
echo [INFO] Press Ctrl+C in this window at any time to pause. Resume anytime!
echo.

.venv\Scripts\python.exe crawlmail\enrich_maps_no_farm.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment process exited with an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Norway agriculture data successfully enriched!
echo ===============================================================================
echo.
pause

