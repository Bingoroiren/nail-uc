@echo off
chcp 65001 >nul
title Loc danh sach thit Bi co Mail hoac SDT - Antigravity IDE

echo =======================================================
echo   LOC DANH SACH THIT BI (BE_MEAT)
echo   Chi giu cac cong ty co EMAIL hoac SDT
echo   Loai bo 100%% cong ty khong co thong tin lien he
echo =======================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
)

echo [*] Dang chay loc va lam sach danh sach thit Bi...
%PYTHON_EXEC% crawlmail\filter_clean_be_meat.py

echo.
echo =======================================================
echo   HOAN TAT! DU LIEU DA DUOC DONG BO VA LUU AN TOAN.
echo =======================================================
pause

