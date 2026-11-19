@echo off
chcp 65001 >nul
title Enrich Lithuania Restaurant and Food Service Data via info.lt

echo ===============================================================================
echo        ENRICH LITHUANIA RESTAURANTS AND FOOD SERVICE DATA VIA INFO.LT
echo                             (LT_FOOD - NACE 56)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt_food.py...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt_food.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Restaurant and Food Service data successfully enriched!
echo ===============================================================================
echo.
pause
