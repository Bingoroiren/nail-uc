@echo off
chcp 65001 >nul
title All-in-One Harvest and Consolidate Lithuania Poultry Dataset

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

echo ==============================================================================
echo [STEP 1/2] Crawling Lithuanian Poultry and Meat Processing Companies
echo Sources: info.lt, ensun.io, rekvizitai.vz.lt
echo Output : LT_POUL_WEBD_0RAW.csv
echo ==============================================================================

%PY_CMD% -u crawlmail\crawl_lt_poultry.py

if errorlevel 1 (
    echo [!] Crawling encountered an issue or was paused.
)

echo.
echo ==============================================================================
echo [STEP 2/2] Consolidating and Formatting Final Cold Mail File
echo Input : LT_POUL_WEBD_0RAW.csv
echo Output: LT_POUL_WEBD_2COL.csv (Single Consolidated 20-Col Cold Mail File)
echo ==============================================================================

%PY_CMD% -u crawlmail\consolidate_lt_poultry.py

echo.
echo [COMPLETED] Single consolidated file generated: LT_POUL_WEBD_2COL.csv
pause
