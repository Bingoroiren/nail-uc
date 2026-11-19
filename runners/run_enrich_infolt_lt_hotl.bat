@echo off
title Enrich Lithuanian Hotels and Accommodation via Info.lt Launcher
cd /d "%~dp0.."

echo ===============================================================================
echo   DATA ENRICHMENT - LITHUANIAN HOTELS AND ACCOMMODATION VIA INFO.LT (NACE 55)
echo   Market   : Lithuania (LT)
echo   Industry : Hotels and Accommodation (HOTL)
echo   Source   : Info.lt Business Directory (INLT)
echo   Input    : LT_HOTL_LTOR_0RAW.csv
echo   Outputs  : LT_HOTL_INLT_1ENR.csv, LT_HOTL_INLT_2COL.csv, LT_HOTL_INLT_ONLY_EMAILS_READY.csv
echo   Sync to  : csdl_mlt/ and archive/lt_lithuania/
echo ===============================================================================

python --version >nul 2>&1
if errorlevel 1 goto NoPython

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b 1

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ===============================================================================
echo Launching Info.lt Enrichment for Lithuanian Hotels...
echo ===============================================================================
python -u crawlmail\enrich_infolt_lt_hotl.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Enrichment completed successfully!
echo Files generated:
echo   - LT_HOTL_INLT_1ENR.csv
echo   - LT_HOTL_INLT_2COL.csv
echo   - LT_HOTL_INLT_ONLY_EMAILS_READY.csv
echo   - csdl_mlt/LT_HOTL_INLT_*.csv
echo   - archive/lt_lithuania/LT_HOTL_INLT_*.csv
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Enrichment script stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo [*] Error: Python is not installed or not in system PATH.
pause
exit /b 1
