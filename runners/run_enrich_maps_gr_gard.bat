@echo off
title Google Maps Data Enrichment for Companies Without Email Launcher
cd /d "%~dp0.."

echo ===============================================================================
echo   GOOGLE MAPS DATA ENRICHMENT PIPELINE (COMPANIES WITHOUT EMAIL)
echo   Target   : GR_GARD_VRIS_2COL.csv (or passed via --input)
echo   Market   : Greece (GR)
echo   Industry : Garden Construction (GARD)
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
echo Launching Google Maps Enrichment Pipeline for No-Email Records...
echo ===============================================================================
python -u crawlmail\enrich_maps_gr_gard.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Google Maps Enrichment completed successfully!
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Enrichment stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo.
echo [ERROR] Python is not installed or not in system PATH.
pause
exit /b 1

