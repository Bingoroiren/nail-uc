@echo off
chcp 65001 >nul
title Cross-reference and Enrich Lithuania Poultry with Food CleanData

echo ========================================================
echo   CROSS-REFERENCE AND ENRICH LT_POUL WITH LT_FOOD
echo   Target: LT_POUL_WEBD_2COL.csv
echo   Source: LT_FOOD_WEBS - CleanData.csv
echo ========================================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Running cross-reference and enrichment...
%PYTHON_EXE% crawlmail\reconcile_lt_poul_food.py

echo.
echo Process completed!
pause

