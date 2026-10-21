@echo off
title Enrich Slovakia Agencies from Workspace Database
cd /d "%~dp0\.."

echo ======================================================
echo    ENRICH SK_AGCY_PERS_0RAW FROM WORKSPACE DATABASE
echo    Target: SK_AGCY_PERS_0RAW.csv
echo    Outputs: SK_AGCY_PERS_1ENR.csv, SK_AGCY_PERS_2COL.csv
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching CSDL cross-reference...
"%PYTHON_EXE%" -u crawlmail\enrich_sk_pers_from_csdl.py

if errorlevel 1 (
    echo.
    echo [!] Enrichment encountered an error.
    pause
    exit /b 1
)

echo.
echo [*] Enrichment from CSDL completed successfully!
pause
