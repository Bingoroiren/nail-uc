@echo off
title Slovakia Philip Google Maps and Web Enrichment
cd /d "%~dp0.."

echo ======================================================
echo    SLOVAKIA PHILIPPINES PRINCIPALS ENRICHMENT
echo    Target: slovakiaphilip.csv
echo    Engine: Google Maps (Playwright) + Deep Website Scraper
echo ======================================================

python --version >nul 2>&1
if errorlevel 1 goto NoPython

if exist .venv goto ActivateVenv
echo [*] Error: Virtual environment .venv not found.
pause
exit /b

:ActivateVenv
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Checking Playwright Chromium...
playwright install chromium >nul 2>&1

echo.
echo ======================================================
echo STEP 1: Launching Google Maps and Website Enrichment...
echo ======================================================
python -u crawlmail/enrich_maps_slovakiaphilip.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    ENRICHMENT COMPLETED SUCCESSFULLY!
echo    Output file: slovakiaphilip.csv
echo ======================================================
pause
goto End

:NoPython
echo [ERROR] Python is not installed or not in your PATH.
pause
exit /b

:RunFailed
echo [ERROR] Enrichment failed during execution.
pause
exit /b

:End
