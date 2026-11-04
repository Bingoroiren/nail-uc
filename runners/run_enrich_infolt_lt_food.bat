@echo off
chcp 65001 >nul
title Enrich Lithuania Food Data via info.lt

echo ===============================================================================
echo        ENRICH LITHUANIA FOOD DATA VIA INFO.LT
echo                     (LT_FOOD)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt.py for Food data...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt.py --target food %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Food data successfully enriched!
echo ===============================================================================
echo.
pause

