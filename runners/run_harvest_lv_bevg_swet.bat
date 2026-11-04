@echo off
chcp 65001 >nul
title Harvest Latvia Sweets Pastries and Beverages (DnB and Kompass)
cd /d "%~dp0\.."

echo =======================================================================
echo   HARVEST LATVIA SWEETS, PASTRIES AND BEVERAGES
echo   Sources: Dun and Bradstreet (Beverages) + Kompass (Pastries and Wholesale)
echo   Output: Separate files (LV_SWET_WEBD_0RAW.csv, LV_SWET_WEBD_2COL.csv)
echo   Visual Chrome Mode: Headless=False
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% csdl_lv_food\harvest_lv_bevg_swet.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT!
echo   Outputs:
echo   - LV_SWET_WEBD_0RAW.csv (Thu muc goc va csdl_lv_food)
echo   - LV_SWET_WEBD_1ENR.csv
echo   - LV_SWET_WEBD_2COL.csv (Chuan 20 cot Cold Mail)
echo =======================================================================
pause
