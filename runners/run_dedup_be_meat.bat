@echo off
chcp 65001 >nul
title Loc trung du lieu thit Bi (BE_MEAT) - Antigravity IDE

echo =======================================================
echo   LOC TRUNG TEN CONG TY VA MA SO KBO THIT BI (BE_MEAT)
echo   Chuan hoa danh sach doanh nghiep doc nhat truoc khi lam giau
echo =======================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
)

echo [*] Dang chay loc trung ten cong ty BE_MEAT_KBO0_0RAW.csv...
%PYTHON_EXEC% crawlmail\deduplicate_kbo_raw.py --file BE_MEAT_KBO0_0RAW.csv

echo.
echo =======================================================
echo   HOAN TAT LOC TRUNG! DU LIEU DA DUOC DONG BO VA LUU AN TOAN.
echo =======================================================
pause

