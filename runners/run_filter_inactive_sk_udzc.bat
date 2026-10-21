@echo off
chcp 65001 >nul
title Loc cong ty khong con hoat dong - SK_UDZC_UPSV_2COL
echo ======================================================================
echo   LOC CONG TY GIAI THE / PHA SAN / KHONG HOAT DONG - SK_UDZC_UPSV_2COL
echo   Doi chieu: Otvoreny register slovenskych firiem (ORSF API) qua ICO
echo ======================================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Dang khoi chay tien trinh kiem tra phap ly va loai bo cong ty dong cua...
echo.

"%PYTHON_EXE%" "crawlmail\filter_inactive_sk_udzc.py"

echo.
echo ======================================================================
echo   DA HOAN TAT TIEN TRINH LOC CONG TY KHONG CON HOAT DONG!
echo ======================================================================
pause
