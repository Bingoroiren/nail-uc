@echo off
chcp 65001 >nul
title Super Master Merge - Korean Shipbuilding and Marine Industry

echo ======================================================================
echo  SUPER MASTER DATASET MERGE - KOREAN SHIPBUILDING AND MARITIME
echo ======================================================================

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

echo [*] Running deep enrichment and super merge...
%PYTHON_EXE% crawlmail\build_ship_super_dataset.py

echo.
echo ======================================================================
echo  COMPLETED! Master files created:
echo  - KR_SHIP_ALLS_2COL.csv (Full 20-col Cold Mail with emails on top)
echo  - KR_SHIP_ALLS_1ENR.csv
echo ======================================================================
pause
