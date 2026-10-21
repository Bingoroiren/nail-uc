@echo off
title Deep Email Enrichment - Lithuania Agencies (LT_AGCY)
cd /d "%~dp0\.."

echo ======================================================
echo    DEEP EMAIL ENRICHMENT - LITHUANIA AGENCIES
echo    Target: LT_AGCY_REKV_2COL.csv
echo    Feature: Multi-threaded Website Deep Crawler
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching email enrichment...
"%PYTHON_EXE%" -u crawlmail\enrich_email_lt_agcy.py

if errorlevel 1 (
    echo.
    echo [!] Enrichment encountered an error.
    pause
    exit /b 1
)

echo.
echo [*] Email enrichment finished successfully!
pause
