@echo off
chcp 65001 >nul
title Greenpages.sk Automotive Enrichment - SK_AUTO_SLVD

echo ======================================================================
echo   GREENPAGES.SK ENRICHMENT - SLOVAK AUTOMOTIVE INDUSTRY
echo   Source      : https://greenpages.sk/en/c/automotive-industry.html
echo   Target File : SK_AUTO_SLVD_1ENR.csv
echo   Module      : High-Authority Automotive Directory Harvester
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

echo [INFO] Crawling Greenpages.sk automotive categories and detail pages...
echo [INFO] Cross-matching and enriching SK_AUTO_SLVD_1ENR.csv...
echo.

"%PYTHON_BIN%" crawlmail\enrich_greenpages_auto.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Process encountered an issue.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo   GREENPAGES ENRICHMENT COMPLETED SUCCESSFULLY!
echo   Results updated in: SK_AUTO_SLVD_1ENR.csv
echo ======================================================================
pause
