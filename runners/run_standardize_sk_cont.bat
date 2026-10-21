@echo off
chcp 65001 >nul
title Chuan hoa va thanh loc nganh xay dung - SK_CONT_STAV_2COL
echo ======================================================================
echo   CHUAN HOA CATEGORY VA LOC BO NGANH PHI XAY DUNG (SK_CONT_STAV_2COL)
echo ======================================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Dang khoi chay tien trinh chuan hoa chuyen nganh va loai bo don vi lech...
echo.

"%PYTHON_EXE%" "formatters\standardize_sk_cont_stav.py"

echo.
echo ======================================================================
echo   DA HOAN TAT CHUAN HOA CHUYEN NGANH XAY DUNG!
echo ======================================================================
pause
