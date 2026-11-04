@echo off
chcp 65001 >nul
title Build Master Food Processing Database for Latvia (LV_FOOD_WEBD)
cd /d "%~dp0\.."

echo =======================================================================
echo   BUILD MASTER FOOD PROCESSING DATABASE - LATVIA (LV_FOOD_WEBD)
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% csdl_lv_food\build_master_lv_food.py

echo.
echo =======================================================================
echo   BUILD COMPLETED!
echo   Outputs:
echo   - csdl_lv_food\LV_FOOD_WEBD_0RAW.csv and LV_FOOD_WEBD_0RAW.csv
echo   - csdl_lv_food\LV_FOOD_WEBD_1ENR.csv and LV_FOOD_WEBD_1ENR.csv
echo   - csdl_lv_food\LV_FOOD_WEBD_2COL.csv and LV_FOOD_WEBD_2COL.csv
echo =======================================================================
pause
