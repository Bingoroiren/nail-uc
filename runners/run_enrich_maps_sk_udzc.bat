@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ======================================================================
echo    STARTING GOOGLE MAPS AND WEB ENRICHMENT FOR SK_UDZC_UPSV_2COL
echo ======================================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

echo Using Python interpreter: %PYTHON_CMD%
echo.
echo Launching Playwright visual browser (headless=False)...
echo Incremental auto-save and 100%% resume checkpoint enabled.
echo.

%PYTHON_CMD% crawlmail\enrich_maps_sk_udzc.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Enrichment script stopped with code %ERRORLEVEL%.
) else (
    echo.
    echo [SUCCESS] Enrichment completed successfully!
)

echo.
pause
