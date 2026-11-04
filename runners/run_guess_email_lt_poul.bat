@echo off
chcp 65001 >nul
title Email Prefix Guessing - Lithuania Poultry and Meat (LT_POUL)
cd /d "%~dp0\.."

echo =======================================================================
echo   EMAIL GUESSING STEP - LITHUANIA POULTRY AND MEAT ENTERPRISES
echo   Dataset: LT_POUL_WEBD_2COL.csv
echo   Logic: Find most popular email prefix and combine with domains
echo =======================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: %PYTHON_EXE%
echo [*] Executing email prefix guessing...
"%PYTHON_EXE%" crawlmail\guess_email_lt_poul.py

if errorlevel 1 (
    echo.
    echo [ERROR] Script encountered an error!
    pause
    exit /b 1
)

echo.
echo =======================================================================
echo   HOAN TAT TIEN TRINH DOAN EMAIL VA DONG BO FILE!
echo   Output:
echo   - LT_POUL_WEBD_2COL.csv (Thu muc goc - 100%% Email len dau)
echo   - LT_POUL_WEBD_1ENR.csv
echo   - csdl_mlt\LT_POUL_WEBD_2COL.csv
echo   - csdl_mlt\LT_POUL_WEBD_1ENR.csv
echo =======================================================================
pause
