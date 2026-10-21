@echo off
chcp 65001 >nul
title Google Maps and Web Enrichment - Slovak Automotive (SK_AUTO_SLVD)

echo ======================================================================
echo   GOOGLE MAPS AND WEB ENRICHMENT - SLOVAK AUTOMOTIVE (NACE 29)
echo   Target File : SK_AUTO_SLVD_1ENR.csv
echo   Checkpoint  : crawlmail\cache_enrich_maps_sk_auto.json
echo   Module      : Deep Rescuer and Precision Multi-Source Enrichment
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

echo [INFO] Starting Deep Rescuer and Precision Enrichment...
echo [INFO] Rescuing missing emails and phones from existing websites...
echo [INFO] Performing precision web search for remaining companies...
echo.

"%PYTHON_BIN%" crawlmail\rescue_and_enrich_auto.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Process encountered an issue or was stopped.
    echo [INFO] Checkpoint is safely saved. You can rerun anytime to resume!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo   ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Results saved to: SK_AUTO_SLVD_1ENR.csv
echo ======================================================================
pause
