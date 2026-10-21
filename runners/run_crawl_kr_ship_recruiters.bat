@echo off
chcp 65001 >nul
title Thu thap Email Moi gioi va Tuyen dung Nhan luc Dong tau Han Quoc

echo ===============================================================================
echo     THU THAP EMAIL MOI GIOI VA TUYEN DUNG NHAN LUC DONG TAU HAN QUOC
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Dang chay thu thap Email moi gioi nhan luc E-7-3 va dong tau...
"%PYTHON_EXE%" crawlmail\crawl_kr_ship_recruiters.py

echo.
echo ===============================================================================
echo Hoan tat! Tep xuat: KR_AGCY_RECR_2COL.csv (100%% Co Email)
echo ===============================================================================
pause
