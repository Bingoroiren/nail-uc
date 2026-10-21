@echo off
chcp 65001 >nul
title Cao Lai Cac Cong Ty Bi Sot D and B Slovakia

echo ======================================================================
echo  CAO LAI CAC CONG TY BI SOT HOAC LOI MANG TU D and B SLOVAKIA
echo ======================================================================
echo.

cd /d "%~dp0\.."

echo [*] Khoi chay trinh cao bo sung (Rescue Missed Companies)...
.venv\Scripts\python.exe csdl_sk_agcy\rescue_missed_dnb.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay rescue_missed_dnb.py
)

echo.
echo ======================================================================
echo  HOAN TAT! KIEM TRA THU MUC: csdl_sk_agcy
echo ======================================================================
pause
