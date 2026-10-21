@echo off
chcp 65001 >nul
title Multi-Portal Cross-Enrichment - Slovak Automotive (SK_AUTO_SLVD)

echo ======================================================================
echo   MULTI-PORTAL CROSS-ENRICHMENT - SLOVAK AUTOMOTIVE INDUSTRY
echo   Target File : SK_AUTO_SLVD_1ENR.csv (Strictly 1,513 Original Records)
echo   Sources     : ZAP SR, Zlate Stranky, Azet, Zoznam, Institucia Firiem
echo   Rule        : Enrich Web, Phone, Mail ONLY. No new rows added!
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

echo [INFO] Harvesting data from all 7 verified portals...
echo [INFO] Cross-matching and enriching existing companies...
echo.

"%PYTHON_BIN%" crawlmail\cross_enrich_multi_portals.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Process encountered an issue.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo   CROSS-ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Results updated in: SK_AUTO_SLVD_1ENR.csv
echo ======================================================================
pause
