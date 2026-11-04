@echo off
chcp 65001 >nul
title Dedup and Filter Mail Tracker - Lithuania Agencies (LT_AGCY)
cd /d "%~dp0\.."

echo =======================================================================
echo   FILTER MAIL TRACKER - LITHUANIA EMPLOYMENT AGENCIES
echo   Target: LT_AGCY_REKV_2COL.csv
echo   Source: Mail Tracker - mail.csv
echo =======================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Executing tracker matching and dedup...
"%PYTHON_EXE%" crawlmail\filter_tracker_lt_agcy.py

if errorlevel 1 (
    echo.
    echo [ERROR] Filter script encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   HOAN TAT DOI CHIEU VA LOC BO TRUNG LAP VOI MAIL TRACKER!
echo =======================================================================
pause
