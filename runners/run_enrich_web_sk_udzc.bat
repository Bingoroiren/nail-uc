@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ======================================================================
echo    STARTING WEB SEARCH AND DEEP CONTACT ENRICHMENT FOR SK_UDZC_UPSV
echo ======================================================================

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_CMD=.venv\Scripts\python.exe
)

echo Using Python interpreter: %PYTHON_CMD%
echo.
echo Launching Web Search (Finding Official Websites + Extracting B2B Emails)...
echo Incremental auto-save and 100%% resume checkpoint enabled.
echo.

%PYTHON_CMD% crawlmail\enrich_web_sk_udzc.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Script stopped with code %ERRORLEVEL%.
) else (
    echo.
    echo [SUCCESS] Web enrichment completed successfully!
)

echo.
pause
