@echo off
chcp 65001 >nul
title Enrich Lithuania Metal Data via info.lt (LT_METL_INLT)

echo ===============================================================================
echo        ENRICH LITHUANIA METAL ENTERPRISES DATA VIA INFO.LT
echo                  (Source: LT_METL_LTOR_0RAW.csv)
echo   Output: LT_METL_INLT_1ENR.csv + LT_METL_INLT_2COL.csv + READY
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [INFO] Running enrich_infolt_lt_metal.py with Pre-Validated Rotating Proxies...
echo.

.venv\Scripts\python.exe crawlmail\enrich_infolt_lt_metal.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Enrichment script encountered an error!
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [SUCCESS] Lithuania Metal enterprises dataset successfully enriched via info.lt!
echo Data saved to:
echo   - LT_METL_INLT_1ENR.csv
echo   - LT_METL_INLT_2COL.csv
echo   - LT_METL_INLT_ONLY_EMAILS_READY.csv
echo ===============================================================================
echo.
pause

