@echo off
chcp 65001 >nul
title Lam giau data moi gioi dong tau Han Quoc - KR_AGCY_SHIP
echo ======================================================================
echo   TIEN TRINH LAM GIAU DU LIEU MOI GIOI NHAN LUC DONG TAU HAN QUOC
echo   Tep nguon: KR_AGCY_SHIP_0RAW.csv
echo   Dau ra:    KR_AGCY_SHIP_1ENR.csv + KR_AGCY_SHIP_2COL.csv
echo ======================================================================
echo.

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Dang bat dau tien trinh tra cuu da tang va boc tach thong tin...
echo.

"%PYTHON_EXE%" "crawlmail\enrich_kr_agcy_ship.py"

echo.
echo ======================================================================
echo   HOAN TAT LAM GIAU DU LIEU!
echo ======================================================================
pause
