@echo off
chcp 65001 >nul
title Google Maps Enrichment - Latvia Food Processing (LV_FOOD_WEBD)
cd /d "%~dp0\.."

echo =======================================================================
echo   GOOGLE MAPS DATA ENRICHMENT - LATVIA FOOD PROCESSING
echo   Dataset: LV_FOOD_WEBD_2COL.csv (Visual Mode - Headless=False)
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% csdl_lv_food\enrich_maps_lv_food.py

echo.
echo =======================================================================
echo   TIEN TRINH HOAN TAT HOAC DA DUOC LUU TANG DAN AN TOAN!
echo   Output:
echo   - LV_FOOD_WEBD_2COL.csv (Thu muc goc - 100%% Email len dau)
echo   - csdl_lv_food\LV_FOOD_WEBD_2COL.csv
echo   - csdl_lv_food\LV_FOOD_WEBD_1ENR.csv
echo =======================================================================
pause
