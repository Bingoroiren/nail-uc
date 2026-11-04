@echo off
chcp 65001 >nul
title Harvest Latvia Labour Agencies from 1188.lv and viss.lv
cd /d "%~dp0\.."

echo ======================================================
echo    HARVEST LATVIA LABOUR AGENCIES (1188.lv + viss.lv)
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\crawl_lv_agcy_webd.py

echo.
echo ======================================================
echo    HARVEST COMPLETED!
echo    - LV_AGCY_WEBD_0RAW.csv
echo    - LV_AGCY_WEBD_1ENR.csv
echo    - LV_AGCY_WEBD_2COL.csv
echo ======================================================
pause
