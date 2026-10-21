@echo off
title Austria Agency Bing Search and Web Enrichment
cd /d "%~dp0.."

echo ======================================================
echo    AUSTRIA MANPOWER AGENCY BING DATA ENRICHMENT
echo    Target: AT_AGCY_SHET_0RAW.csv
echo    Output: AT_AGCY_SHET_1ENR.csv
echo    Engine: Bing Search (curl_cffi) + Deep Web Scraper
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

echo.
echo ======================================================
echo STEP 1: Launching Bing Search and Deep Web Enrichment...
echo ======================================================
python -u crawlmail/enrich_bing_at_agcy_shet.py
if errorlevel 1 goto RunFailed

echo.
echo ======================================================
echo    ENRICHMENT COMPLETED SUCCESSFULLY!
echo    Output file: AT_AGCY_SHET_1ENR.csv
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
