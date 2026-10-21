@echo off
chcp 65001 >nul
title Rekvizitai.vz.lt Harvester - Visual Mode
cd /d "%~dp0\.."

echo =======================================================================
echo   REKVIZITAI.VZ.LT HARVESTER (Visual Browser Mode)
echo   Category: Fisheries and Fish Products
echo =======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe csdl_mlt\harvest_rekvizitai.py

echo.
echo =======================================================================
echo   REKVIZITAI HARVEST COMPLETED!
echo   Output: csdl_mlt\rekvizitai_database.csv
echo =======================================================================
pause
