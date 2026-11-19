@echo off
title Litorg.cc Lithuanian Hotels and Accommodation (NACE 55) Scraper Launcher
cd /d "%~dp0.."

echo ===============================================================================
echo   LITORG.CC SCRAPER - LITHUANIAN HOTELS AND ACCOMMODATION (NACE 55)
echo   Market   : Lithuania (LT)
echo   Industry : Hotels and Accommodation (HOTL)
echo   Source   : Litorg Business Directory (LTOR)
echo   Scope    : NACE 55 (Hotels, Short-stay, Camping, Lodging - 26 pages)
echo   Outputs  : LT_HOTL_LTOR_0RAW.csv, LT_HOTL_LTOR_2COL.csv
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
echo Launching Litorg.cc Scraper for NACE 55...
echo ===============================================================================
python -u src\scraper_lt_hotl_litorg.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Scraping completed successfully!
echo Files generated:
echo   - LT_HOTL_LTOR_0RAW.csv
echo   - LT_HOTL_LTOR_2COL.csv
echo   - csdl_mlt/LT_HOTL_LTOR_*.csv
echo   - archive/lt_lithuania/LT_HOTL_LTOR_*.csv
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Scraper stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo [*] Error: Python is not installed or not in system PATH.
pause
exit /b 1
