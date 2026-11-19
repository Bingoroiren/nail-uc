@echo off
title Vrisko.gr Greek Garden Construction Scraper and Email Enricher Launcher
cd /d "%~dp0.."

echo ===============================================================================
echo   VRISKO.GR GREEK GARDEN CONSTRUCTION SCRAPER AND EMAIL ENRICHER PIPELINE
echo   Market   : Greece (GR)
echo   Industry : Garden Construction (GARD)
echo   Source   : Vrisko Business Directory (VRIS)
echo   Outputs  : GR_GARD_VRIS_0RAW.csv, 1ENR.csv, 2COL.csv, ONLY_EMAILS_READY.csv
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
echo Launching Vrisko.gr Scraper and Email Enrichment Pipeline...
echo ===============================================================================
python -u src\scraper_vrisko_gr_gard.py %*
if errorlevel 1 goto RunFailed

echo.
echo ===============================================================================
echo [SUCCESS] Pipeline execution finished successfully!
echo Files generated:
echo   - GR_GARD_VRIS_0RAW.csv
echo   - GR_GARD_VRIS_1ENR.csv
echo   - GR_GARD_VRIS_2COL.csv
echo   - GR_GARD_VRIS_ONLY_EMAILS_READY.csv
echo   - gr_greece\GR_GARD_VRIS_*.csv
echo ===============================================================================
pause
exit /b 0

:RunFailed
echo.
echo [ERROR] Pipeline stopped with errors. Check console output above.
pause
exit /b 1

:NoPython
echo.
echo [ERROR] Python is not installed or not in system PATH.
pause
exit /b 1

