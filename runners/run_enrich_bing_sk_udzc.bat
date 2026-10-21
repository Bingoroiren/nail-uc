@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ======================================================================
echo    STARTING BING WEB SEARCH ENRICHMENT FOR SK_UDZC_UPSV_2COL
echo ======================================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

echo Using Python interpreter: %PYTHON_CMD%
echo.
echo Running Bing Search + Deep Web Crawler (Fast and Resilient)...
echo Incremental auto-save and 100%% resume checkpoint enabled.
echo.

%PYTHON_CMD% crawlmail\enrich_bing_sk_udzc.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script stopped with code %ERRORLEVEL%.
) else (
    echo.
    echo [SUCCESS] Enrichment completed successfully!
)

echo.
pause
