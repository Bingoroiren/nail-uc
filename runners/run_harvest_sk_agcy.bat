@echo off
chcp 65001 >nul
title CSDL Moi Gioi Lao Dong Slovakia (Staffing and Employment Agencies)

echo ======================================================================
echo  THU THAP VA CHUAN HOA CSDL MOI GIOI LAO DONG SLOVAKIA
echo ======================================================================
echo.

cd /d "%~dp0\.."

echo [1/3] Dang cao personalneagentury.sk...
.venv\Scripts\python.exe csdl_sk_agcy\harvest_personalneagentury.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay harvest_personalneagentury.py
)

echo.
echo [2/3] Dang cao greenpages.sk...
.venv\Scripts\python.exe csdl_sk_agcy\harvest_greenpages_agcy.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay harvest_greenpages_agcy.py
)

echo.
echo [3/3] Dang tong hop va xuat du lieu chuan 2COL...
.venv\Scripts\python.exe csdl_sk_agcy\consolidate_sk_agcy.py
if %ERRORLEVEL% NEQ 0 (
    echo [-] Loi xay ra khi chay consolidate_sk_agcy.py
)

echo.
echo ======================================================================
echo  HOAN TAT! KIEM TRA THU MUC: csdl_sk_agcy
echo ======================================================================
pause
