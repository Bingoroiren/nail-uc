@echo off
chcp 65001 >nul
title Cao D and B Dun and Bradstreet Employment Services Slovakia

echo ======================================================================
echo  CAO DANH SACH EMPLOYMENT SERVICES SLOVAKIA TU DUN AND BRADSTREET
echo ======================================================================
echo.

cd /d "%~dp0\.."

echo [*] Khoi chay trinh cao D and B Slovakia (Playwright Chromium)...
.venv\Scripts\python.exe csdl_sk_agcy\scrape_dnb_slovakia.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay scrape_dnb_slovakia.py
)

echo.
echo ======================================================================
echo  HOAN TAT! KIEM TRA THU MUC: csdl_sk_agcy
echo ======================================================================
pause
