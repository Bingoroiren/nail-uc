@echo off
chcp 65001 >nul
title Google Maps and Web Enrichment - Austria Agriculture (AT_AGRI_WBIO)

echo ======================================================================
echo   ENRICHMENT GOOGLE MAPS AND WEB CRAWLER - AUSTRIA AGRICULTURE
echo   Input : AT_AGRI_WBIO_0RAW.csv (Unique and Deduplicated)
echo   Output: AT_AGRI_WBIO_1ENR.csv
echo   Checkpoint: crawlmail\cache_enrich_maps_at_agri.json
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

echo [INFO] Starting Google Maps and Email Enrichment...
echo [INFO] Browser will launch in visual mode (headless=False).
echo [INFO] In case of Captcha, solve it directly in the browser window.
echo.

"%PYTHON_BIN%" crawlmail\enrich_maps_at_agri.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script encountered an issue or was interrupted.
    echo [INFO] Checkpoint is saved. You can re-run anytime to resume!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo   ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Results saved to: AT_AGRI_WBIO_1ENR.csv
echo ======================================================================
pause
