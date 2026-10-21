@echo off
chcp 65001 >nul
title Enrich Korean Shipping Companies via Google Maps
cd /d "%~dp0\.."

echo ======================================================
echo    ENRICH KOREAN SHIPPING DATA VIA GOOGLE MAPS
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_maps_kr_ship.py

echo.
echo ======================================================
echo    ENRICHMENT TASK COMPLETED!
echo ======================================================
pause
