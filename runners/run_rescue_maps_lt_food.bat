@echo off
title Google Maps Rescue Enrichment for Lithuanian Restaurants (LT_FOOD_LTOR)
cd /d "%~dp0.."

echo ===============================================================================
echo   GOOGLE MAPS RESCUE - LITHUANIAN RESTAURANTS AND CATERING (NO EMAIL)
echo   Target   : LT_FOOD_LTOR_2COL.csv (4,214 companies)
echo   Market   : Lithuania (LT)
echo   Industry : Food and Restaurants (FOOD)
echo   Strategy : Smart Name Match + Google Maps Place Cards + Deep Website Crawl
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
echo Launching Google Maps Rescue for LT_FOOD_LTOR_2COL.csv...
echo ===============================================================================
python -u crawlmail\rescue_maps_lt_food.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Google Maps Rescue completed successfully!
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Rescue stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo.
echo [ERROR] Python is not installed or not in system PATH.
pause
exit /b 1

