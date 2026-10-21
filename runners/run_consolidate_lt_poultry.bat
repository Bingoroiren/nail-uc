@echo off
title Lithuania Poultry Consolidation and Cold Mail Formatter
cd /d "%~dp0\.."

echo ======================================================
echo    LITHUANIA POULTRY CONSOLIDATION AND COLD MAIL
echo    Input : LT_POUL_WEBD_0RAW.csv
echo    Output: LT_POUL_WEBD_1ENR.csv, LT_POUL_WEBD_2COL.csv
echo    Feature: Deep B2B Email Crawl + 100%% Mails on Top
echo ======================================================

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Launching consolidator...
"%PYTHON_EXE%" -u crawlmail\consolidate_lt_poultry.py

if errorlevel 1 (
    echo.
    echo [!] Consolidator encountered an error.
    pause
    exit /b 1
)

echo.
echo [*] Consolidation and Cold Mail formatting completed!
pause
