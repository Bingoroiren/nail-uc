@echo off
chcp 65001 >nul
title Enrich Lithuania Food and Poultry Data via info.lt

echo ===============================================================================
echo        ENRICH LITHUANIA FOOD AND POULTRY DATA VIA INFO.LT
echo                     (LT_POUL and LT_FOOD)
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt.py for both Poultry and Food datasets...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt.py --target all %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Both Lithuania datasets successfully enriched!
echo ===============================================================================
echo.
pause

