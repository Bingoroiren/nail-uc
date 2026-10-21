@echo off
title Slovakia Employment Agencies Google Maps Enrichment
cd /d "%~dp0\.."

echo ======================================================
echo    SLOVAKIA AGENCIES GOOGLE MAPS ENRICHMENT
echo    Input : SK_AGCY_PERS_0RAW.csv
echo    Output: SK_AGCY_PERS_1ENR.csv, SK_AGCY_PERS_2COL.csv
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching enrichment...
"%PYTHON_EXE%" -u crawlmail\enrich_maps_sk_pers.py

if errorlevel 1 (
    echo.
    echo [!] Enrichment exited with an error.
    pause
    exit /b 1
)

echo.
echo [*] Enrichment finished successfully!
pause
