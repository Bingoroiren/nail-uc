@echo off
title Master Email and Phone Enrichment - Slovakia Agencies
cd /d "%~dp0\.."

echo ======================================================
echo    MASTER EMAIL AND PHONE ENRICHMENT - SLOVAKIA AGENCIES
echo    Target: SK_AGCY_PERS_2COL.csv
echo    Feature: Multi-threaded Deep Crawl + Registry + MX Verify
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching Master Enrichment...
"%PYTHON_EXE%" -u crawlmail\enrich_master_sk_pers.py

if errorlevel 1 (
    echo.
    echo [!] Master Enrichment encountered an error.
    pause
    exit /b 1
)

echo.
echo [*] Master Enrichment finished successfully!
pause
