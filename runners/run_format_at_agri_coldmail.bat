@echo off
chcp 65001 >nul
title Format Cold Mail - Austria Agriculture (AT_AGRI_WBIO_2COL)

echo ======================================================================
echo   FORMAT COLD MAIL DATASET - AUSTRIA AGRICULTURE
echo   Input : AT_AGRI_WBIO_1ENR.csv
echo   Output: AT_AGRI_WBIO_2COL.csv (Standard 20 Columns for Cold Mail)
echo ======================================================================
echo.

cd /d "%~dp0\.."

set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

"%PYTHON_BIN%" formatters\format_at_agri_coldmail.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Formatting script encountered an issue.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo   FORMATTING COMPLETED SUCCESSFULLY!
echo   Results saved to: AT_AGRI_WBIO_2COL.csv
echo ======================================================================
pause
