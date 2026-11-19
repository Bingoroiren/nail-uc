@echo off
title Litorg.cc Lithuanian Restaurants and Catering (56.1 and 56.2) Scraper Launcher
cd /d "%~dp0.."

echo ===============================================================================
echo   LITORG.CC SCRAPER - LITHUANIAN RESTAURANTS AND CATERING (NACE 56.1 AND 56.2)
echo   Market   : Lithuania (LT)
echo   Industry : Food and Restaurants (FOOD)
echo   Source   : Litorg Business Directory (LTOR)
echo   Scope    : 56.1 Restaurants (66 pages) + 56.2 Catering (20 pages)
echo   Outputs  : LT_FOOD_LTOR_0RAW.csv, LT_FOOD_LTOR_2COL.csv
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
echo Launching Litorg.cc Scraper for 56.1 and 56.2...
echo ===============================================================================
python -u src\scraper_lt_food_litorg.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Scraping completed successfully!
echo Files generated:
echo   - LT_FOOD_LTOR_0RAW.csv
echo   - LT_FOOD_LTOR_2COL.csv
echo   - csdl_mlt/LT_FOOD_LTOR_*.csv
echo   - archive/lt_lithuania/LT_FOOD_LTOR_*.csv
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Scraper stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo.
echo [ERROR] Python is not installed or not in system PATH.
pause
exit /b 1

