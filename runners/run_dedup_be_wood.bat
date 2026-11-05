@echo off
chcp 65001 >nul
title Loc trung du lieu go Bi (BE_WOOD) - Antigravity IDE

echo =======================================================
echo   LOC TRUNG TEN CONG TY VA MA SO KBO GO BI (BE_WOOD)
echo   Chuan hoa danh sach doanh nghiep doc nhat truoc khi lam giau
echo =======================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
)

echo [*] Dang chay loc trung ten cong ty BE_WOOD_KBO0_0RAW.csv...
%PYTHON_EXEC% crawlmail\deduplicate_kbo_raw.py --file BE_WOOD_KBO0_0RAW.csv

echo.
echo =======================================================
echo   HOAN TAT LOC TRUNG! DU LIEU DA DUOC DONG BO VA LUU AN TOAN.
echo =======================================================
pause

