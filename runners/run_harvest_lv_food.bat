@echo off
chcp 65001 >nul
title Harvest Latvia Food and Beverage Catalogs
cd /d "%~dp0\.."

echo =======================================================================
echo   HARVEST LATVIA FOOD AND BEVERAGE DATASETS
echo =======================================================================
echo.

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

echo [1/5] Harvesting Latvian Foods Cluster Members...
%PYTHON_CMD% csdl_lv_food\harvest_latvianfoods.py

echo.
echo [2/5] Harvesting EC TRACES NT Approved Establishments...
%PYTHON_CMD% csdl_lv_food\harvest_traces_food.py

echo.
echo [3/5] Harvesting 1188.lv Food and Seafood Catalogs...
%PYTHON_CMD% csdl_lv_food\harvest_1188_food.py

echo.
echo [4/5] Harvesting Dun and Bradstreet Latvia Beverage Directory...
%PYTHON_CMD% csdl_lv_food\harvest_dnb_beverage.py

echo.
echo [5/5] Building Master Latvia Food Database...
%PYTHON_CMD% csdl_lv_food\build_master_lv_food.py

echo.
echo =======================================================================
echo   HARVEST AND BUILD COMPLETED SUCCESSFULLY!
echo =======================================================================
pause
