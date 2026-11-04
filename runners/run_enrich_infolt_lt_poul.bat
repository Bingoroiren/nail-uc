@echo off
chcp 65001 >nul
title Enrich Lithuania Poultry Data via info.lt

echo ===============================================================================
echo        ENRICH LITHUANIA POULTRY DATA VIA INFO.LT
echo                     (LT_POUL)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt.py for Poultry data...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt.py --target poul %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Poultry data successfully enriched!
echo ===============================================================================
echo.
pause

