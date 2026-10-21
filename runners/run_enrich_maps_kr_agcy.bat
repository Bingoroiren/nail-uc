@echo off
chcp 65001 >nul
title Enrich Korean Employment Agencies via Google Maps
cd /d "%~dp0\.."

echo ======================================================
echo    ENRICH KR AGCY DATA VIA GOOGLE MAPS (KR_AGCY_NVER)
echo ======================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

%PYTHON_CMD% crawlmail\enrich_maps_kr_agcy.py

echo.
echo ======================================================
echo    ENRICHMENT TASK COMPLETED!
echo ======================================================
pause
